from flask.templating import render_template
from flask import request, escape, Response
from update import MongoStorage, StashServer, fetch_all, fetch_single
import datetime
import flask
import operator
import os
from StringIO import StringIO

#===================================================================================================
# app init
#===================================================================================================
app = flask.Flask('todo-dashboard')

#===================================================================================================
# /
#===================================================================================================
@app.route('/')
def index():
    import config 
    
    storage = MongoStorage()
    
    entries = list(storage.iter_all_todos())
    entries = sorted(entries, key=operator.itemgetter('repo'))
    href_format = config.git_repo_url + '/projects/{proj}/repos/{slug}/browse/{filename}#{lineno}'
    for entry in entries:
        for todo in entry['todos']:
            proj, slug = StashServer.split_repo_name(entry['repo'])
            format_params = entry.copy()
            format_params.update(proj=proj, slug=slug, lineno=todo['lineno'])
            todo['href'] = href_format.format(**format_params)
            if todo['days']: 
                todo['days_as_timedelta'] = datetime.timedelta(days=todo['days'])

    date, elapsed = storage.get_last_fetch_all_status()
              
    return render_template('dashboard.html', entries=entries, date=date, elapsed=elapsed)


#===================================================================================================
# /fetch
#===================================================================================================
@app.route('/fetch', methods=['GET', 'POST'])
@app.route('/fetch/<project>/<slug>', methods=['GET', 'POST'])
def fetch(project=None, slug=None):
    import config
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        auth = (username, password)
        stream = StringIO()
        if project is not None and slug is not None:
            repo_name = '{}/{}'.format(project, slug)
            fetch_single(config.git_repo_url, repo_name, auth, stream=stream)
            return '<pre>{}</pre>'.format(escape(stream.getvalue()))
        else:
            def generate():
                '''
                Incrementally generate data to return it to the browser as soon as it is available.
                '''
                read_bytes = 0
                for _ in fetch_all(config.git_repo_url, config.search_projects, auth, stream=stream):
                    stream.seek(read_bytes)
                    contents = stream.read()
                    yield '<pre>{}</pre>'.format(escape(contents))
                    read_bytes += len(contents)
                    
            return Response(generate())
    else:
        return render_template('login.html')
    

#===================================================================================================
# main
#===================================================================================================
if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')))

