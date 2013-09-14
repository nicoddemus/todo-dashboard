from StringIO import StringIO
from ast import Expression
from pip.vcs.git import urlsplit
import ast
import datetime
import fnmatch
import futures
import optparse
import os
import pymongo
import requests
import sys
import time


#===================================================================================================
# StashServer
#===================================================================================================
class StashServer(object):
    
    
    def __init__(self, base_url, auth):
        self._base_url = base_url
        self._auth = auth
        
        
    @classmethod
    def split_repo_name(cls, repo_name):
        fields = repo_name.split('/')
        assert len(fields) in (1, 2)
        project = fields[0]
        if len(fields) == 2:
            slug = fields[1]
        else:
            slug = None
        
        return project, slug
        
        
    def _make_repo_url_api(self, repo_name, api):
        project, slug = self.split_repo_name(repo_name)
        result = '%s/rest/api/1.0/projects/%s/repos' % (self._base_url, project)
        if slug:
            result += '/%s' % slug
        if api:
            if not api.startswith('/'):
                api = '/' + api
            result += api
        return result
    
    
    def _check_reponse(self, response):
        if response.status_code != 200:
            raise RuntimeError('Response status %d. Text:\n%s' % (response.status_code, response.text))
    
    
    def _iter_paged_requests(self, url, params={}):
        params = params.copy()
        while True:
            r = requests.get(url, params=params, auth=self._auth)
            self._check_reponse(r)
            
            json = r.json()
            yield json
            
            if json['isLastPage']:
                break
            params['start'] = json['nextPageStart']
            
                
    def get_branches(self, repo_name):
        url = self._make_repo_url_api(repo_name, '/branches')
        
        result = {}
        for json in self._iter_paged_requests(url, params=dict(limit=1000)):
            for value in json['values']:
                result[value['id']] = value['latestChangeset']   
        return result
        

    def iter_file_names(self, repo_name, since=None, until=None, at=None):
        params = {'limit': 1000}
        
        if until is not None:
            assert at is not None, "either pass 'since' and 'until' params or 'at'"
            params['until'] = until
            if since is not None:
                params['since'] = since
                
            url = self._make_repo_url_api(repo_name, '/changes')
            for json in self._iter_paged_requests(url, params):
                for value in json['values']:
                    yield value['path']['toString']
        else:
            if at is not None:
                params['at'] = at
            url = self._make_repo_url_api(repo_name, '/files')
            for json in self._iter_paged_requests(url, params):
                for filename in json['values']:
                    yield filename
        
        
    def get_file_contents(self, repo_name, filename, at=None):
        params = {'raw': 1}
        if at is not None:
            params['at'] = at
            
        project, slug = self.split_repo_name(repo_name)
        url = '%s/projects/%s/repos/%s/browse/%s' % (self._base_url, project, slug, filename)
        
        r = requests.get(url, params=params, auth=self._auth)
        if r.status_code == 200:
            return r.text
        else:
            return None
        
        
    def iter_repos(self, project_name):
        for json in self._iter_paged_requests(self._make_repo_url_api(project_name, api=None)):
            for value in json['values']:
                yield value['slug']
        

#===================================================================================================
# MongoStorage
#===================================================================================================
class MongoStorage(object):
    
    def __init__(self, default_db_name='todos'):
        mongodb_uri = os.environ.get('MONGOLAB_URI', 'mongodb://localhost:27017/{}'.format(default_db_name))
        db_name = urlsplit(mongodb_uri).path[1:]
        self._connection = pymongo.Connection(mongodb_uri)
        self._db = self._connection[db_name]
        
        self._db.todos.create_index([('repo', pymongo.ASCENDING), ('filename', pymongo.ASCENDING)])
        self._db.hashes.create_index('repo')
        
        self.__TESTING__ = False
        
        
    def get_connection(self):
        assert self.__TESTING__
        return self._connection
    
        
    def drop_all(self):
        self._db.drop_collection('todos')
        self._db.drop_collection('hashes')
        self._db.drop_collection('fetch_all_status')
        
        
    def drop_todos_for_repo(self, repo_name):
        result = False
        for entry in self._db.todos.find({'repo': repo_name}):
            self._db.todos.remove(entry['_id'])
            result = True
            
        entry = self._db.hashes.find_one({'repo': repo_name})
        if entry:
            self._db.hashes.remove(entry['_id'])
            result = True
        
        return result
         

    def update_todos(self, repo_name, filename, todos):
        entry = self._db.todos.find_one({'repo': repo_name, 'filename': filename})
        if todos:
            if entry is None:
                entry = {}
            entry['repo'] = repo_name
            entry['filename'] = filename
            entry['todos'] = todos
            self._db.todos.save(entry)
        else:
            if entry is not None:
                self._db.todos.remove(entry['_id'])
                
                
    def iter_all_todos(self):
        return iter(self._db.todos.find())
    
    
    def get_last_hash(self, repo_name):
        entry = self._db.hashes.find_one({'repo': repo_name})
        if entry:
            return entry['hash']
        else:
            return None
        
        
    def set_last_hash(self, repo_name, hash_value):
        entry = self._db.hashes.find_one({'repo': repo_name})
        if entry is None:
            entry = {'repo': repo_name}
        entry['hash'] = hash_value
        self._db.hashes.save(entry)


    def set_last_fetch_all_status(self, date, elapsed):
        entry = self._db.fetch_all_status.find_one()
        if entry is None:
            entry = {}
        entry['date'] = date.strftime('%Y-%m-%d %H:%M:%S')
        entry['elapsed'] = str(elapsed)
        self._db.fetch_all_status.save(entry)


    def get_last_fetch_all_status(self):
        entry = self._db.fetch_all_status.find_one()
        if entry is not None:
            return entry['date'], entry['elapsed']
        else:
            return None, None
    
    
#===================================================================================================
# IterToDos
#===================================================================================================
def IterToDos(contents):
    
    class MyVisitor(ast.NodeVisitor):

        def __init__(self):
            self.todos = []
        
        
        def IsToDo(self, expr):
            return type(expr) is ast.Call and expr.func.id == 'ToDo'
        
        def visit_FunctionDef(self, function_def):
            if function_def.decorator_list and self.IsToDo(function_def.decorator_list[0]):
                call = function_def.decorator_list[0]
                
                function_name = function_def.name
                
                if call.args:
                    date = ast.literal_eval(call.args[0])
                    date = datetime.datetime(*date)
                else:
                    date = None
                
                if date is not None and call.keywords:
                    expr = Expression(call.keywords[0].value)
                    b = compile(expr, '', 'eval')
                    
                    days = eval(b)
                else:
                    days = None
                    
                self.todos.append({
                    'function_name' : function_name, 
                    'date' : date, 
                    'days' : days, 
                    'lineno' : function_def.lineno,
                })
    
    visitor = MyVisitor()
    try:
        visitor.visit(ast.parse(contents))
    except SyntaxError:
        return
    
    for x in visitor.todos:
        yield x    
        
        
#===================================================================================================
# fetch
#===================================================================================================
def fetch(repo_name, storage, stash, stream):
    branches = stash.get_branches(repo_name)
    
    def short(hash_name):
        return hash_name[:7]
    
    start_time = time.time()
    
    try:
        master = branches['refs/heads/master']
    except KeyError:
        print >> stream, 'Skipping: no master branch'
        print >> stream, 'Branches (%d):' % len(branches)
        for branch in branches:
            print >> stream, branch
        return
    
    last_hash = storage.get_last_hash(repo_name)
    
    if last_hash == master:
        print >> stream, 'ToDos up-to-date (against %s)' % short(master)
    else:
        if last_hash:
            since = last_hash
            until = master
            print >> stream, 'Fetching %s %s..%s' % (repo_name, short(since), short(until))
        else:
            print >> stream, 'Fetching %s ALL (master at %s)' % (repo_name, short(master))
            since = None
            until = None
        
        filenames = list(stash.iter_file_names(repo_name, since=since, until=until))
        print >> stream, 'Changed Files: %d' % len(filenames)
        
        filenames = [x for x in filenames if fnmatch.fnmatch(os.path.basename(x), 'test_*.py')]
        print >> stream, 'Test Files: %d' % len(filenames)
        
        summary = {}
        for filename in filenames:
            contents = stash.get_file_contents(repo_name, filename, at=until)
            if contents is not None:
                todos = list(IterToDos(contents))
            else:
                todos = []
            
            if todos:
                stream.write('T')
                summary[filename] = len(todos)
            else:
                stream.write('.')

            storage.update_todos(repo_name, filename, todos)
                
        storage.set_last_hash(repo_name, master)
        
        print >> stream
        print >> stream, '  Summary for %s (took %.2f seconds) ---' % (repo_name, time.time()-start_time)
        print >> stream, '  ToDos: %d' % sum(summary.itervalues())
        if summary:
            for filename, count in summary.iteritems(): 
                print >> stream, '  -', filename, count        
                
        
#===================================================================================================
# fetch_all
#===================================================================================================
def fetch_all(git_repo_url, search_projects, auth=None, stream=sys.stdout):
    storage, stash = _init_fetch(git_repo_url, auth)
    start_time = time.time()
    
    exclude = set(['etk'])
    repos = []
    for project in search_projects:
        repos += ['{}/{}'.format(project, slug) for slug in stash.iter_repos(project) if slug not in exclude]
    
    with futures.ThreadPoolExecutor(max_workers=8) as executor:
        
        # submit fetch jobs for each repo, creating a mapping future => (repo_name, sub_stream)
        future_to_repo = {}
        for repo_name in repos:
            sub_stream = StringIO()
            future = executor.submit(fetch, repo_name, storage, stash, sub_stream)
            future_to_repo[future] = (repo_name, sub_stream)
        
        # as fetches get gone, print its status along with sub-stream contents
        for index, future in enumerate(futures.as_completed(future_to_repo)):
            percent = int(((index + 1.0) / len(repos)) * 100.0)
            repo_name, sub_stream = future_to_repo[future]
            print >> stream, '=== Fetched %s (%d of %d: %d%%) ===' % (repo_name, index + 1, len(repos), percent)
            print >> stream, sub_stream.getvalue()
            yield 
    
    print >> stream
    total_seconds = time.time()-start_time
    print >> stream, 'Total Time:', total_seconds
    storage.set_last_fetch_all_status(datetime.datetime.today(), datetime.timedelta(seconds=total_seconds))
    
    
#===================================================================================================
# fetch_single
#===================================================================================================
def fetch_single(git_repo_url, repo_name, auth=None, stream=sys.stdout):    
    storage, stash = _init_fetch(git_repo_url, auth)
    print >> stream, '=== Fetching %s ===' % (repo_name)
    fetch(repo_name, storage, stash, stream)


#===================================================================================================
# _init_fetch
#===================================================================================================
def _init_fetch(git_repo_url, auth):
    storage = MongoStorage()
    
    stash = StashServer(git_repo_url, auth=auth)
    return storage, stash
    
    
#===================================================================================================
# drop_todos
#===================================================================================================
def drop_todos(repo_name):
    storage = MongoStorage()
    if storage.drop_todos_for_repo(repo_name):
        print 'Dropped ToDos for %s' % repo_name
    else:
        print 'No ToDos registered for %s' % repo_name
            

#===================================================================================================
# drop_all
#=================================================================================================== 
def drop_all():
    answer = raw_input('This will drop ALL tables. Next update will refresh all todos from scratch.'
        '\nProceed? (type "YES") ')
    if answer == 'YES':
        storage = MongoStorage()
        storage.drop_all()
        print 'All tables dropped.'


#===================================================================================================
# main
#===================================================================================================
def main(argv):    
    parser = optparse.OptionParser()
    parser.add_option('--drop', type=str)
    parser.add_option('--drop-all', action='store_true', default=False)
    parser.add_option('--fetch', type=str)
    options, _ = parser.parse_args(argv)

    import config

    if options.drop:
        drop_todos(options.drop)
    elif options.fetch:
        fetch_single(config.git_repo_url, options.fetch, auth=config.auth)
    elif options.drop_all:
        drop_all()
    else:
        # ugly hack to consume the entire generator... think of a better way to handle this
        list(fetch_all(config.git_repo_url, config.search_projects, auth=config.auth))
        
    return 0
    
    
#===================================================================================================
# entry point
#===================================================================================================
if __name__ == '__main__':
    sys.exit(main(sys.argv))
    
    
   
