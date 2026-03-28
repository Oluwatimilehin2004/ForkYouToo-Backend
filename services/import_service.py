# services/import_service.py
import requests
import base64
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class GitHubImportService:
    """Service to handle repository import/fork with customization"""
    
    def __init__(self, access_token):
        self.access_token = access_token
        self.headers = {
            'Authorization': f'token {access_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.base_url = "https://api.github.com"
    
    def fork_repository(self, owner, repo_name):
        """Fork a repository to the authenticated user's account"""
        url = f"{self.base_url}/repos/{owner}/{repo_name}/forks"
        
        try:
            response = requests.post(url, headers=self.headers)
            
            if response.status_code == 202:
                logger.info(f"Fork initiated for {owner}/{repo_name}")
                return response.json()
            else:
                logger.error(f"Fork failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Fork error: {e}")
            return None
    
    def get_user_repos(self):
        """Get list of user's repositories"""
        url = f"{self.base_url}/user/repos"
        params = {'per_page': 100, 'sort': 'updated'}
        
        response = requests.get(url, headers=self.headers, params=params)
        return response.json() if response.status_code == 200 else []
    
    def get_repo_contents(self, owner, repo_name, path=""):
        """Get contents of a repository directory"""
        url = f"{self.base_url}/repos/{owner}/{repo_name}/contents/{path}"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            return response.json()
        return None
    
    def create_file(self, owner, repo_name, file_path, content, commit_message):
        """Create a file in a repository"""
        url = f"{self.base_url}/repos/{owner}/{repo_name}/contents/{file_path}"
        
        # Encode content to base64
        encoded_content = base64.b64encode(content.encode()).decode()
        
        data = {
            'message': commit_message,
            'content': encoded_content
        }
        
        response = requests.put(url, headers=self.headers, json=data)
        return response.status_code == 201 or response.status_code == 200
    
    def update_file(self, owner, repo_name, file_path, content, sha, commit_message):
        """Update an existing file"""
        url = f"{self.base_url}/repos/{owner}/{repo_name}/contents/{file_path}"
        
        encoded_content = base64.b64encode(content.encode()).decode()
        
        data = {
            'message': commit_message,
            'content': encoded_content,
            'sha': sha
        }
        
        response = requests.put(url, headers=self.headers, json=data)
        return response.status_code == 200
    
    def rename_project_in_readme(self, owner, repo_name, old_name, new_name):
        """Rename project references in README"""
        # Get README file
        readme_url = f"{self.base_url}/repos/{owner}/{repo_name}/readme"
        response = requests.get(readme_url, headers=self.headers)
        
        if response.status_code == 200:
            readme_data = response.json()
            content = base64.b64decode(readme_data['content']).decode('utf-8')
            sha = readme_data['sha']
            
            # Replace project name
            new_content = content.replace(old_name, new_name)
            new_content = new_content.replace(old_name.upper(), new_name.upper())
            new_content = new_content.replace(old_name.capitalize(), new_name.capitalize())
            
            # Update README
            return self.update_file(
                owner, repo_name, 'README.md', new_content, sha,
                f"Rename project from {old_name} to {new_name}"
            )
        
        return False
    
    def rename_in_settings_py(self, owner, repo_name, old_name, new_name):
        """Rename project in Django settings.py if exists"""
        settings_path = "settings.py"
        url = f"{self.base_url}/repos/{owner}/{repo_name}/contents/{settings_path}"
        
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            file_data = response.json()
            content = base64.b64decode(file_data['content']).decode('utf-8')
            sha = file_data['sha']
            
            # Replace settings
            new_content = content.replace(old_name, new_name)
            
            return self.update_file(
                owner, repo_name, settings_path, new_content, sha,
                f"Rename project to {new_name}"
            )
        
        return False


class RepoCustomizer:
    """Customize imported repository with various options"""
    
    def __init__(self, import_service, owner, repo_name):
        self.service = import_service
        self.owner = owner
        self.repo_name = repo_name
    
    def rename_project(self, old_name, new_name):
        """Rename project across the repository"""
        changes = []
        
        # Update README
        if self.service.rename_project_in_readme(self.owner, self.repo_name, old_name, new_name):
            changes.append('README.md')
        
        # Update settings.py (for Django projects)
        if self.service.rename_in_settings_py(self.owner, self.repo_name, old_name, new_name):
            changes.append('settings.py')
        
        return changes
    
    def add_import_note(self, original_repo_url):
        """Add import note to README"""
        note = f"""
---
## 📦 Imported from [{original_repo_url}]({original_repo_url})
*Imported using ForkYouToo - Learn, Adapt, Build*
"""
        
        # Append to README
        readme_url = f"https://api.github.com/repos/{self.owner}/{self.repo_name}/readme"
        response = requests.get(readme_url, headers=self.service.headers)
        
        if response.status_code == 200:
            readme_data = response.json()
            content = base64.b64decode(readme_data['content']).decode('utf-8')
            sha = readme_data['sha']
            
            new_content = content + note
            
            return self.service.update_file(
                self.owner, self.repo_name, 'README.md', new_content, sha,
                "Add import attribution note"
            )
        
        return False