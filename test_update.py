from update import MongoStorage, StashServer
import datetime
import pytest



#===================================================================================================
# storage
#===================================================================================================
@pytest.fixture
def storage(request):
    '''
    Initializes a MongoStorage() using a test-specific data-base, to avoid any conflicts between
    tests and to avoid clashing with real databases.
    '''
    db_name = 'testing-{}'.format(request.node.name)
    
    result = MongoStorage(default_db_name=db_name)
    result.__TESTING__ = True
    
    def finalizer():
        result.get_connection().drop_database(db_name)
        
    request.addfinalizer(finalizer)
    return result
    

#===================================================================================================
# TestMongoStorage
#===================================================================================================
class TestMongoStorage(object):
    '''
    Tests for MongoStorage class. Requires a MongoDB running. 
    '''
    
    def make_todo_dict(self, function_name, date, days, lineno):
        return {
            'function_name': function_name, 
            'date': date, 
            'days': days,
            'lineno': lineno,
        }
        
        
    def discard_ids(self, entries):
        entries = list(entries)
        for entry in entries:
            del entry['_id']
        return list(entries)
        
    
    def test_todos(self, storage):
        assert list(storage.iter_all_todos()) == []
        
        # push and check todos for 'foo'
        foo_todos = [
            self.make_todo_dict('test_foo1', datetime.datetime(2013, 9, 8), 5, 200),
            self.make_todo_dict('test_foo2', datetime.datetime(2013, 9, 24), 10, 500),
        ]
        storage.update_todos('proj/repo1', 'src/foo.py', foo_todos)
        assert self.discard_ids(storage.iter_all_todos()) == [
            {
                'repo': 'proj/repo1',
                'filename': 'src/foo.py',
                'todos': foo_todos,
            },
        ]
        
        # change date and make sure it reflects back
        foo_todos[0]['date'] = datetime.datetime(2014, 9, 8)
        storage.update_todos('proj/repo1', 'src/foo.py', foo_todos)
        assert self.discard_ids(storage.iter_all_todos()) == [
            {
                'repo': 'proj/repo1',
                'filename': 'src/foo.py',
                'todos': foo_todos,
            },
        ]
        
        # add todos for 'bar'
        bar_todos = [
            self.make_todo_dict('test_bar1', datetime.datetime(2013, 5, 8), 15, 600),
        ]
        storage.update_todos('proj/repo2', 'src/bar.py', bar_todos)
        assert self.discard_ids(storage.iter_all_todos()) == [
            {
                'repo': 'proj/repo1',
                'filename': 'src/foo.py',
                'todos': foo_todos,
            },
            {
                'repo': 'proj/repo2',
                'filename': 'src/bar.py',
                'todos': bar_todos,
            },
        ]
        
        # remove todos for 'foo' and make sure 'bar' todos are still ok
        storage.update_todos('proj/repo1', 'src/foo.py', [])
        assert self.discard_ids(storage.iter_all_todos()) == [
            {
                'repo': 'proj/repo2',
                'filename': 'src/bar.py',
                'todos': bar_todos,
            },
        ]
        
        
    def test_last_hash(self, storage):
        assert storage.get_last_hash('proj/repo1') is None
        assert storage.get_last_hash('proj/repo2') is None
        
        storage.set_last_hash('proj/repo1', '11111')
        assert storage.get_last_hash('proj/repo1') == '11111'
        assert storage.get_last_hash('proj/repo2') is None
        
        storage.set_last_hash('proj/repo2', '22222')
        assert storage.get_last_hash('proj/repo1') == '11111'
        assert storage.get_last_hash('proj/repo2') == '22222'
        
        
    def test_last_fetch_all_status(self, storage):
        assert storage.get_last_fetch_all_status() == (None, None)
        
        date = datetime.datetime(2013, 9, 8, 23, 30, 0)
        storage.set_last_fetch_all_status(date, datetime.timedelta(seconds=40))
        
        assert storage.get_last_fetch_all_status() == ('2013-09-08 23:30:00', '0:00:40')
        
        
#===================================================================================================
# stash_server
#===================================================================================================
@pytest.fixture        
def stash_server(request, repo_name):
    server = StashServer(request.config.option.stash_url, auth=None)
    proj_name = repo_name.split('/')[0]
    assert 'todo-dashboard-test' in set(server.iter_repos(proj_name))
    return server


#===================================================================================================
# repo_name
#===================================================================================================
@pytest.fixture        
def repo_name(request):
    return request.config.option.stash_repo
            
            
#===================================================================================================
# TestStashServer
#===================================================================================================
@pytest.mark.skipif('not config.option.stash_url or not config.option.stash_repo')
class TestStashServer(object):     
    
    REPO_NAME = '~bruno/todo-dashboard-test'
    
    def test_iter_file_names(self, stash_server, repo_name):
        expected = set([
            '.gitignore', 
            'README.md', 
            'foo/foo1.py', 
            'foo/foo2.py', 
            'main.py',
        ])
        
        assert set(stash_server.iter_file_names(repo_name)) == expected
        at = stash_server.get_branches(repo_name)['refs/heads/master']
        assert set(stash_server.iter_file_names(repo_name, at=at)) == expected
           
        at = stash_server.get_branches(repo_name)['refs/heads/bar_branch']
        assert set(stash_server.iter_file_names(repo_name, at=at)) == set([
            '.gitignore', 
            'README.md', 
            'bar/bar1.py', 
            'foo/foo1.py', 
            'foo/foo2.py', 
            'main.py',
        ])   
        
        
    def test_branches(self, stash_server, repo_name):
        assert stash_server.get_branches(repo_name) == {
            'refs/heads/master' : '43c918485bf46630d1d8d5ee65e19d0effb32f1f',
            'refs/heads/bar_branch' : '3ee46863fdc113418f41019e868ed4597fb924b5',
        }
        
        
    def test_get_file_contents(self, stash_server, repo_name):
        
        def split_contents(contents): 
            return [x.rstrip() for x in contents.splitlines() if x.strip()]
        
        lines = split_contents(stash_server.get_file_contents(repo_name, 'foo/foo1.py'))
        assert lines == [
            'class Foo1:',
            '    def hello(self):',
            "        print 'foo1'",
        ]
        
        at = stash_server.get_branches(repo_name)['refs/heads/bar_branch']
        lines = split_contents(stash_server.get_file_contents(repo_name, 'bar/bar1.py', at=at))
        assert lines == [
            'class Bar1:',
            '    def hey(self):',
            "        print 'bar1'",
        ]
        
        
#===================================================================================================
# main
#===================================================================================================
if __name__ == '__main__':        
    pytest.main(['', '-s'])        