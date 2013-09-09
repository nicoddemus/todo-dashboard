from update import MongoStorage
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
        
        
#===================================================================================================
# main
#===================================================================================================
if __name__ == '__main__':        
    pytest.main(['', '-s'])        