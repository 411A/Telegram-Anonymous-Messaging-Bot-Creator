import os
import hashlib
import difflib
import aiofiles
import aiohttp
import asyncio
from .responses import get_response, ResponseKey
from typing import Final

DIFFERENCES_FILE_NAME: Final = "all_differences.md"
DEVELOPER_GITHUB_USERNAME: Final = "411A"
DEVELOPER_GITHUB_REPOSITORY_NAME: Final = "Telegram-Anonymous-Messaging-Bot-Creator"

class GitHubChecker:
    def __init__(self, repo_owner, repo_name, branch="main", ignore_files=None, ignore_folders=None):
        """
        Initialize the GitHubChecker.

        Parameters:
            repo_owner (str): GitHub repository owner.
            repo_name (str): GitHub repository name.
            branch (str): Repository branch to check (default "main").
            ignore_files (list): List of filenames to ignore (default [".env"]).
            ignore_folders (list): List of folder names to ignore (default [".venv", "__pycache__", ".git"]).
        """
        self.local_dir = self._get_running_file_dir()
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.branch = branch
        self.ignore_files = ignore_files if ignore_files is not None else [".env"]
        self.ignore_folders = ignore_folders if ignore_folders is not None else [".venv", "__pycache__", ".git"]
        self._check_state = None  # Stores the check results after running once
        self._has_run = False
        self.gitignore_patterns = list()
        # Load .gitignore patterns asynchronously (fire and forget)
        asyncio.create_task(self._load_gitignore())

    async def _load_gitignore(self):
        """Load patterns from .gitignore file if it exists."""
        gitignore_path = os.path.join(self.local_dir, ".gitignore")
        if os.path.exists(gitignore_path):
            async with aiofiles.open(gitignore_path, 'r') as f:
                async for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Remove trailing slashes for consistency
                        pattern = line.rstrip('/')
                        self.gitignore_patterns.append(pattern)
                        # If it's a file pattern (no slashes), add it to ignore_files
                        if '/' not in pattern:
                            self.ignore_files.append(pattern)
                        # If it ends with a slash or contains a slash, it's a folder pattern
                        elif pattern.endswith('/') or '/' in pattern:
                            folder = pattern.rstrip('/')
                            if folder not in self.ignore_folders:
                                self.ignore_folders.append(folder)

    def _get_running_file_dir(self):
        """Get the root directory of the project."""
        # Get the directory of the currently running file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up one level to get to the project root
        return os.path.dirname(current_dir)

    async def _get_file_hash(self, filepath, algorithm="sha256"):
        """Compute the hash of a file."""
        hasher = hashlib.new(algorithm)
        async with aiofiles.open(filepath, "rb") as f:
            while chunk := await f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    async def _hash_file_entry(self, filepath):
        """Hash a file and return its relative path with its hash."""
        rel_path = os.path.relpath(filepath, self.local_dir)
        file_hash = await self._get_file_hash(filepath)
        return rel_path, file_hash

    async def _get_local_hashes(self):
        """Generate hashes for all local files (ignoring specified files and folders)."""
        local_hashes = dict()
        files_to_hash = list()

        for root, _, files in os.walk(self.local_dir):
            rel_root = os.path.relpath(root, self.local_dir)
            # Skip ignored folders
            if any(ignored in root for ignored in self.ignore_folders):
                continue
            # Skip folders matching gitignore patterns
            if self._matches_gitignore(os.path.join(rel_root, '')):
                continue

            for file in files:
                # Skip files in ignore list
                if file in self.ignore_files:
                    continue
                rel_path = os.path.join(rel_root, file)
                if self._matches_gitignore(rel_path):
                    continue
                files_to_hash.append(os.path.join(root, file))

        tasks = [self._hash_file_entry(f) for f in files_to_hash]
        results = await asyncio.gather(*tasks)
        local_hashes = dict(results)
        return local_hashes

    def _matches_gitignore(self, path):
        """Check if a path matches any gitignore pattern."""
        from fnmatch import fnmatch
        path = path.replace('\\', '/')
        for pattern in self.gitignore_patterns:
            if pattern.endswith('/'):
                # Directory pattern
                if fnmatch(path + '/', pattern + '*'):
                    return True
            else:
                # File pattern
                if fnmatch(path, pattern):
                    return True
        return False

    async def _fetch_and_hash_github_file(self, item, session):
        """Fetch a file from GitHub and compute its hash.
        
        Skip files that are in the ignore list.
        """
        # Check if file should be ignored (using basename)
        if os.path.basename(item["path"]) in self.ignore_files:
            return None

        file_url = f"https://raw.githubusercontent.com/{self.repo_owner}/{self.repo_name}/{self.branch}/{item['path']}"
        async with session.get(file_url) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch {file_url}: Status {response.status}")
            content = await response.read()
            file_hash = hashlib.sha256(content).hexdigest()
        return item["path"], file_hash

    async def _get_github_hashes(self):
        """Fetch all GitHub file hashes (ignoring specified files)."""
        github_hashes = dict()
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/git/trees/{self.branch}?recursive=1"
        headers = {"Accept": "application/vnd.github.v3+json"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"GitHub API error: {response.status}")
                repo_data = await response.json()

            blob_items = [
                item for item in repo_data.get("tree", [])
                if item["type"] == "blob" and os.path.basename(item["path"]) not in self.ignore_files
            ]
            tasks = [self._fetch_and_hash_github_file(item, session) for item in blob_items]
            results = await asyncio.gather(*tasks)
            for result in results:
                if result is not None:
                    path, file_hash = result
                    github_hashes[path] = file_hash

        return github_hashes

    async def check_integrity(self, user_lang):
        """Compare local source code with GitHub repository.
        This method runs only once; subsequent calls return the stored check-state.

        Args:
            user_lang (str): Language code ('en' or 'fa')

        Returns:
            list: A list of messages indicating the state of the repository.
        """
        if self._has_run:
            return self._check_state

        responses = list()

        msg = get_response(ResponseKey.FETCHING_LOCAL_FILES, user_lang)
        print(msg)
        local_hashes = await self._get_local_hashes()

        msg = get_response(ResponseKey.LOCAL_FILES_HASHED, user_lang).format(len(local_hashes))
        print(msg)
        responses.append(msg)

        msg = get_response(ResponseKey.FETCHING_GITHUB_FILES, user_lang)
        print(msg)
        github_hashes = await self._get_github_hashes()

        msg = get_response(ResponseKey.GITHUB_FILES_HASHED, user_lang).format(len(github_hashes))
        print(msg)
        responses.append(msg)

        if local_hashes == github_hashes:
            msg = get_response(ResponseKey.SOURCE_IDENTICAL, user_lang)
            print(msg)
            responses.append(msg)
        else:
            msg = get_response(ResponseKey.SOURCE_DIFFERS, user_lang)
            print(msg)
            responses.append(msg)
            for file, local_hash in local_hashes.items():
                if file not in github_hashes:
                    msg = get_response(ResponseKey.EXTRA_FILE, user_lang).format(file)
                    print(msg)
                    responses.append(msg)
                elif github_hashes.get(file) != local_hash:
                    msg = get_response(ResponseKey.MODIFIED_FILE, user_lang).format(file)
                    print(msg)
                    responses.append(msg)
            for file in github_hashes:
                if file not in local_hashes:
                    msg = get_response(ResponseKey.MISSING_FILE, user_lang).format(file)
                    print(msg)
                    responses.append(msg)

        self._check_state = responses
        self._has_run = True
        return responses

    async def write_line_differences(self):
        """
        Compute the exact line differences for modified files (present in both local and GitHub,
        but with differing content) and write them to a file named DIFFERENCES_FILE_NAME.
        
        The report follows this structure:
        
            file_relative_path
            +<added line>
            -<removed line>
        
        File paths are relative to the current working directory.
        """
        # Recompute local and GitHub hashes to identify modified files.
        local_hashes = await self._get_local_hashes()
        github_hashes = await self._get_github_hashes()

        modified_files = [
            file for file in local_hashes
            if file in github_hashes and local_hashes[file] != github_hashes[file]
        ]

        output_path = os.path.join(os.getcwd(), DIFFERENCES_FILE_NAME)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        async with aiofiles.open(output_path, "w", encoding="utf-8") as outfile:
            if not modified_files:
                return "IDENTICAL_FILES"
            for file in modified_files:
                # Compute relative file path from current working directory.
                local_file_path = os.path.join(self.local_dir, file)
                rel_path = os.path.relpath(local_file_path, os.getcwd())

                try:
                    async with aiofiles.open(local_file_path, "r", encoding="utf-8") as f:
                        local_content = (await f.read()).splitlines()
                except Exception:
                    local_content = list()

                file_url = f"https://raw.githubusercontent.com/{self.repo_owner}/{self.repo_name}/{self.branch}/{file}"
                github_content = list()
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(file_url) as response:
                            if response.status == 200:
                                text = await response.text()
                                github_content = text.splitlines()
                except Exception:
                    github_content = list()

                diff_lines = list(difflib.ndiff(github_content, local_content))
                # Filter only the lines that indicate additions or removals.
                diff_filtered = [line for line in diff_lines if line.startswith('+ ') or line.startswith('- ')]

                if diff_filtered:
                    # Write the file header and its differences.
                    await outfile.write(f"### {rel_path}\n")
                    await outfile.write("```diff\n")
                    for line in diff_filtered:
                        await outfile.write(f"{line}\n")
                    await outfile.write("```\n")
