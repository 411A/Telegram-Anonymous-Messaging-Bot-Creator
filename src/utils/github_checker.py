import os
import hashlib
import difflib
import aiofiles
import aiohttp
import asyncio
from fnmatch import fnmatch
from .responses import get_response, ResponseKey
from configs.settings import PROJECT_GITHUB_URL, DIFFERENCES_FILE_NAME


class GitHubChecker:
    """
    Checks the integrity of local source code against a GitHub repository.
    This optimized version uses SHA-1 hashing to match Git's own object hashes,
    allowing it to verify all remote files with a single API call.
    """
    def __init__(self, repo_owner, repo_name, branch="main", ignore_files=None, ignore_folders=None):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.branch = branch
        self.local_dir = self._get_project_root()
        
        # Initialize ignore lists, including common defaults
        self.ignore_files = set(ignore_files if ignore_files is not None else [".env", DIFFERENCES_FILE_NAME])
        self.ignore_folders = set(ignore_folders if ignore_folders is not None else [".venv", "__pycache__", ".git"])
        
        self.gitignore_patterns = []
        
        # Caching attributes to store results after the first run
        self.local_hashes = None
        self.github_hashes = None
        self._check_state = None
        self._has_run_check = False
        
        # Asynchronously load .gitignore patterns upon instantiation
        asyncio.create_task(self._load_gitignore())

    async def _load_gitignore(self):
        """Asynchronously loads and parses patterns from the .gitignore file."""
        gitignore_path = os.path.join(self.local_dir, ".gitignore")
        if not os.path.exists(gitignore_path):
            return
        
        async with aiofiles.open(gitignore_path, 'r') as f:
            lines = await f.readlines()
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    self.gitignore_patterns.append(stripped)

    def _get_project_root(self):
        """Determines the project's root directory."""
        if os.environ.get("DOCKER_ENV"):  # Check if running in a known Docker environment
            return '/app'
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Assuming this file is in .../src/utils, navigate up to the root
        return os.path.dirname(os.path.dirname(current_dir))

    async def _get_git_sha1_hash(self, filepath):
        """
        Computes the SHA-1 hash of a file in the same way Git does,
        including the "blob" header.
        """
        hasher = hashlib.sha1()
        async with aiofiles.open(filepath, "rb") as f:
            content = await f.read()
            # Git prefixes file content with "blob <size>\0" before hashing
            header = f"blob {len(content)}\0".encode('utf-8')
            hasher.update(header + content)
        return hasher.hexdigest()

    def _is_ignored(self, path):
        """Checks if a given path (file or folder) should be ignored."""
        path = path.replace('\\', '/')
        
        # Check against simple ignore lists first
        if os.path.basename(path) in self.ignore_files:
            return True
        if any(f"/{folder}/" in f"/{path}/" for folder in self.ignore_folders):
            return True
            
        # Check against .gitignore patterns
        for pattern in self.gitignore_patterns:
            if fnmatch(path, pattern) or fnmatch(os.path.basename(path), pattern):
                return True
            if pattern.endswith('/') and path.startswith(pattern.rstrip('/')):
                return True
        return False

    def _collect_files_to_hash_sync(self):
        """Synchronously walks the directory tree and collects files, respecting ignores."""
        files_to_hash = []
        for root, dirs, files in os.walk(self.local_dir, topdown=True):
            # Prune ignored directories to prevent walking them
            dirs[:] = [d for d in dirs if not self._is_ignored(os.path.join(os.path.relpath(root, self.local_dir), d))]
            
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), self.local_dir)
                if not self._is_ignored(rel_path):
                    files_to_hash.append(os.path.join(self.local_dir, rel_path))
        return files_to_hash

    async def _get_local_hashes(self):
        """Asynchronously generates SHA-1 hashes for all non-ignored local files."""
        if self.local_hashes is not None:
            return self.local_hashes

        loop = asyncio.get_running_loop()
        # Run the synchronous file-walking in a thread pool to avoid blocking
        files_to_hash = await loop.run_in_executor(None, self._collect_files_to_hash_sync)
        
        tasks = [self._hash_file_entry(f) for f in files_to_hash]
        results = await asyncio.gather(*tasks)
        
        self.local_hashes = dict(results)
        return self.local_hashes

    async def _hash_file_entry(self, filepath):
        """Helper to hash a file and return its relative path and hash."""
        rel_path = os.path.relpath(filepath, self.local_dir).replace('\\', '/')
        file_hash = await self._get_git_sha1_hash(filepath)
        return rel_path, file_hash

    async def _get_github_hashes(self):
        """
        Gets all file hashes from GitHub in a single API call.
        This is the core optimization.
        """
        if self.github_hashes is not None:
            return self.github_hashes
            
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/git/trees/{self.branch}?recursive=1"
        headers = {"Accept": "application/vnd.github.v3+json"}
        github_hashes = {}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status() # Raise an exception for bad status codes
                repo_data = await response.json()

        for item in repo_data.get("tree", []):
            if item["type"] == "blob" and not self._is_ignored(item["path"]):
                github_hashes[item["path"]] = item["sha"]
        
        self.github_hashes = github_hashes
        return self.github_hashes

    async def check_integrity(self, user_lang):
        """
        Compares local source code with the GitHub repository.
        Results are cached after the first run.
        """
        if self._has_run_check:
            return self._check_state

        responses = []
        try:
            # Concurrently fetch local and remote hashes
            print(get_response(ResponseKey.FETCHING_LOCAL_FILES, user_lang))
            local_hashes_task = asyncio.create_task(self._get_local_hashes())
            
            print(get_response(ResponseKey.FETCHING_GITHUB_FILES, user_lang))
            github_hashes_task = asyncio.create_task(self._get_github_hashes())

            local_hashes, github_hashes = await asyncio.gather(local_hashes_task, github_hashes_task)
            
            msg_local = get_response(ResponseKey.LOCAL_FILES_HASHED, user_lang).format(len(local_hashes))
            print(msg_local)
            responses.append(msg_local)

            msg_github = get_response(ResponseKey.GITHUB_FILES_HASHED, user_lang, PROJECT_GITHUB_URL=PROJECT_GITHUB_URL, number=len(github_hashes))
            print(msg_github)
            responses.append(msg_github)

            if local_hashes == github_hashes:
                msg = get_response(ResponseKey.SOURCE_IDENTICAL, user_lang)
                print(msg)
                responses.append(msg)
            else:
                msg = get_response(ResponseKey.SOURCE_DIFFERS, user_lang)
                print(msg)
                responses.append(msg)
                
                local_files = set(local_hashes.keys())
                github_files = set(github_hashes.keys())

                for file in sorted(local_files - github_files):
                    responses.append(get_response(ResponseKey.EXTRA_FILE, user_lang).format(file))
                
                for file in sorted(github_files - local_files):
                    responses.append(get_response(ResponseKey.MISSING_FILE, user_lang).format(file))
                
                for file in sorted(local_files & github_files):
                    if local_hashes[file] != github_hashes[file]:
                        responses.append(get_response(ResponseKey.MODIFIED_FILE, user_lang).format(file))

        except aiohttp.ClientError as e:
            error_msg = f"Network error checking repository: {e}"
            print(error_msg)
            responses.append(error_msg)
        except Exception as e:
            error_msg = f"An unexpected error occurred: {e}"
            print(error_msg)
            responses.append(error_msg)

        self._check_state = responses
        self._has_run_check = True
        return responses

    async def write_line_differences(self):
        """
        Computes and writes exact line differences for modified files to a report file.
        Reuses cached hashes if available.
        """
        # Check if the caches are empty and compute them if needed.
        if self.local_hashes is None or self.github_hashes is None:
            await asyncio.gather(self._get_local_hashes(), self._get_github_hashes())

        # Assure the linter that the variables are not None
        assert self.local_hashes is not None, "Local hashes should not be None here"
        assert self.github_hashes is not None, "GitHub hashes should not be None here"

        modified_files = [
            file for file in self.local_hashes
            if file in self.github_hashes and self.local_hashes[file] != self.github_hashes[file]
        ]

        if not modified_files:
            return "IDENTICAL_FILES"

        output_path = os.path.join(os.getcwd(), DIFFERENCES_FILE_NAME)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        async with aiohttp.ClientSession() as session:
            async with aiofiles.open(output_path, "w", encoding="utf-8") as outfile:
                for file in sorted(modified_files):
                    local_path = os.path.join(self.local_dir, file)
                    remote_url = f"https://raw.githubusercontent.com/{self.repo_owner}/{self.repo_name}/{self.branch}/{file}"
                    
                    # Fetch local and remote content concurrently
                    local_content_task = asyncio.create_task(self._read_local_file(local_path))
                    remote_content_task = asyncio.create_task(self._fetch_remote_file(session, remote_url))
                    local_content, github_content = await asyncio.gather(local_content_task, remote_content_task)
                    
                    diff_lines = list(difflib.ndiff(github_content, local_content))
                    diff_filtered = [line for line in diff_lines if line.startswith('+ ') or line.startswith('- ')]

                    if diff_filtered:
                        rel_path = os.path.relpath(local_path, os.getcwd()).replace('\\', '/')
                        await outfile.write(f"### {rel_path}\n```diff\n")
                        await outfile.write("".join(f"{line}\n" for line in diff_filtered))
                        await outfile.write("```\n\n")

    async def _read_local_file(self, path):
        """Safely reads local file content."""
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                return (await f.read()).splitlines()
        except IOError:
            return []

    async def _fetch_remote_file(self, session, url):
        """Safely fetches remote file content."""
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    return (await response.text()).splitlines()
                return []
        except aiohttp.ClientError:
            return []
