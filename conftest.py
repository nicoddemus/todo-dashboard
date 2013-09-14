#===================================================================================================
# pytest_addoption
#===================================================================================================
def pytest_addoption(parser):
    '''
    Adds a new "--jenkins-available" option to pytest's command line. If not given, tests that
    require a live Jenkins instance will be skipped.
    '''
    parser.addoption(
        "--stash-url", 
        action="store", 
        help="url to stash server",
    )
    parser.addoption(
        "--stash-repo", 
        action="store", 
        help="name of the stash repository to use for testing",
    )
