import os
import hashlib
import requests
import difflib
from concurrent.futures import ThreadPoolExecutor
from responses import get_response, ResponseKey
from configs.constants import DIFFERENCES_FILE_NAME

class GitHubChecker:
    def __init__(self, repo_owner, repo_name, branch="main", ignore_files=None, ignore_folders=None):
        """
        Initialize the GitHubChecker.

        Parameters:
            repo_owner (str): GitHub repository owner.
            repo_name (str): GitHub repository name.
            branch (str): Repository branch to check (default "main").
            ignore_files (list): List of filenames to ignore (default [".env"]).
            ignore_folders (list): List of folder names to ignore (default ["__pycache__"]).
        """
        self.local_dir = self._get_running_file_dir()
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.branch = branch
        self.ignore_files = ignore_files if ignore_files is not None else [".env"]
        self.ignore_folders = ignore_folders if ignore_folders is not None else ["__pycache__", ".git"]
        self._check_state = None  # Stores the check results after running once
        self._has_run = False
        self._load_gitignore()

    def _load_gitignore(self):
        """Load patterns from .gitignore file if it exists."""
        gitignore_path = os.path.join(self.local_dir, ".gitignore")
        self.gitignore_patterns = []
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r') as f:
                for line in f:
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

    def _get_file_hash(self, filepath, algorithm="sha256"):
        """Compute the hash of a file."""
        hasher = hashlib.new(algorithm)
        with open(filepath, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _hash_file_entry(self, filepath):
        """Hash a file and return its relative path with its hash."""
        rel_path = os.path.relpath(filepath, self.local_dir)
        return rel_path, self._get_file_hash(filepath)

    def _get_local_hashes(self):
        """Generate hashes for all local files (ignoring specified files and folders)."""
        local_hashes = {}
        file_list = []

        for root, dirs, files in os.walk(self.local_dir):
            # Prune ignored directories from os.walk's dirs list to prevent traversal
            dirs[:] = [d for d in dirs if d not in self.ignore_folders]
            
            rel_root = os.path.relpath(root, self.local_dir)
            # Skip processing if any part of the path is ignored
            components = rel_root.split(os.path.sep)
            if any(comp in self.ignore_folders for comp in components):
                continue

            for file in files:
                if file in self.ignore_files:
                    continue
                rel_path = os.path.join(rel_root, file) if rel_root != '.' else file
                if any(self._matches_gitignore(rel_path) for pattern in self.gitignore_patterns):
                    continue
                file_list.append(os.path.join(root, file))

        with ThreadPoolExecutor() as executor:
            results = executor.map(lambda f: self._hash_file_entry(f), file_list)
            local_hashes = {k: v for k, v in results if k is not None}

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

    def _fetch_and_hash_github_file(self, item):
        """Fetch a file from GitHub and compute its hash.
        
        Skip files that are in the ignore list.
        """
        # Check if file should be ignored (using basename)
        if os.path.basename(item["path"]) in self.ignore_files:
            return None

        file_url = f"https://raw.githubusercontent.com/{self.repo_owner}/{self.repo_name}/{self.branch}/{item['path']}"
        response = requests.get(file_url)
        response.raise_for_status()
        file_hash = hashlib.sha256(response.content).hexdigest()
        return item["path"], file_hash

    def _get_github_hashes(self):
        """Fetch all GitHub file hashes (ignoring specified files)."""
        github_hashes = {}
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/git/trees/{self.branch}?recursive=1"
        headers = {"Accept": "application/vnd.github.v3+json"}

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"GitHub API error: {response.status_code}")

        repo_data = response.json()
        # Only consider files (blobs) and filter out ignored files
        blob_items = [
            item for item in repo_data.get("tree", []) 
            if item["type"] == "blob" and os.path.basename(item["path"]) not in self.ignore_files
        ]

        with ThreadPoolExecutor() as executor:
            # Map returns None for ignored files, so we filter those out.
            results = list(executor.map(lambda item: self._fetch_and_hash_github_file(item), blob_items))
            for result in results:
                if result is not None:
                    path, file_hash = result
                    github_hashes[path] = file_hash

        return github_hashes

    def check_integrity(self, user_lang):
        """
        Compare local source code with GitHub repository.
        This method runs only once; subsequent calls return the stored check-state.

        Args:
            user_lang (str): Language code ('en' or 'fa')

        Returns:
            list: A list of messages indicating the state of the repository.
        """
        if self._has_run:
            return self._check_state

        responses = []

        msg = get_response(ResponseKey.FETCHING_LOCAL_FILES, user_lang)
        print(msg)
        local_hashes = self._get_local_hashes()

        msg = get_response(ResponseKey.LOCAL_FILES_HASHED, user_lang).format(len(local_hashes))
        print(msg)
        responses.append(msg)

        msg = get_response(ResponseKey.FETCHING_GITHUB_FILES, user_lang)
        print(msg)
        github_hashes = self._get_github_hashes()

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

    def write_line_differences(self):
        """
        Compute the exact line differences for modified files (present in both local and GitHub,
        but with differing content) and write them to a file named DIFFERENCES_FILE_NAME.
        
        The report follows this structure:
        
            file_relative_path
            +<added line>
            -<removed line>
        
        File paths are relative to the current working directory (i.e. where main.py is run).
        """
        # Recompute local and GitHub hashes to identify modified files.
        local_hashes = self._get_local_hashes()
        github_hashes = self._get_github_hashes()
        
        modified_files = [
            file for file in local_hashes
            if file in github_hashes and local_hashes[file] != github_hashes[file]
        ]
        
        output_path = os.path.join(os.getcwd(), DIFFERENCES_FILE_NAME)
        
        with open(output_path, "w", encoding="utf-8") as outfile:
            if not modified_files:
                return "IDENTICAL_FILES"
            for file in modified_files:
                # Compute relative file path from current working directory.
                local_file_path = os.path.join(self.local_dir, file)
                rel_path = os.path.relpath(local_file_path, os.getcwd())
                
                # Read local file content.
                try:
                    with open(local_file_path, "r", encoding="utf-8") as f:
                        local_content = f.read().splitlines()
                except Exception:
                    local_content = []
                
                # Fetch GitHub file content.
                file_url = f"https://raw.githubusercontent.com/{self.repo_owner}/{self.repo_name}/{self.branch}/{file}"
                try:
                    response = requests.get(file_url)
                    response.raise_for_status()
                    github_content = response.text.splitlines()
                except Exception:
                    github_content = []
                
                # Generate diff using difflib.ndiff.
                diff_lines = list(difflib.ndiff(github_content, local_content))
                # Filter only the lines that indicate additions or removals.
                diff_filtered = [line for line in diff_lines if line.startswith('+ ') or line.startswith('- ')]
                
                # If there are actual differences, write them to the output file
                if diff_filtered:
                    # Write the file header and its differences.
                    outfile.write(f"{rel_path}\n")
                    for line in diff_filtered:
                        outfile.write(f"{line}\n")
                    outfile.write("\n")  # Separate each file's diff with a newline.
