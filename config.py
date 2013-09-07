'''
Class to centralize dashboard's global configuration access, such as git repo url, authentication,
etc.
'''
import os

git_repo_url = os.environ['TODO_DASHBOARD_GIT_URL']
auth = tuple(os.environ['TODO_DASHBOARD_AUTH'].split(':'))
search_projects = os.environ['TODO_DASHBOARD_PROJECTS'].split(os.sep)