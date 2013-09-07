# TODO Dashboard #

Web application that displays a list of *TODO* markers in git repositories.

It updates its internal database of *TODO* entries periodically by scanning the repositories source
files. This scanning is cheap after the first time, because it remembers which hash 
was scanned last time and only scans new files changed since then.

The application was designed to be deployed on [Heroku](http://www.heroku.com), but it should be
straighforward to deploy it in any cloud service or local network.

## Requirements ##

The application is written for **Python 2.7**, using [Flask](http://flask.pocoo.org/) for its
web framework and [MongoDB](http://api.mongodb.org/python/current/) for its database.

This are the main requirements, for a complete list consult [requirements.txt](requirements.txt).

## Limitations ##

This project is in its early stages, and there are a number of limitations:

* At the moment only works with [Stash](https://www.atlassian.com/software/stash/) servers. Github and
  local git repositories are planned.
* The markup searched to identify *TODO* entries in code is limited, but will be configurable in 
  the future. 

## Configuration ##

The following environment variables must be available for it to work:

* `TODO_DASHBOARD_GIT_URL`: full url to stash server. Example `https://www.example.com/stash`. 
* `TODO_DASHBOARD_AUTH`: authentication, given as a pair `user:pass`. 
* `TODO_DASHBOARD_PROJECTS`: list of projects to scan. All repositories of each project will be 
  scanned, and this should be set to a comma-separated list.
  
This variables should be configured remotely using the `heroku config:set` command.

## Updating the Database ##

You should periodically execute `update.py` in [Heroku](http://www.heroku.com) in order to 
update the database. 

You can easily configure [Heroku Scheduler](https://addons.heroku.com/scheduler)
to do this periodically. Alternatively, you can `POST` to `/fetch` url in order to start a
full update or to `/fetch/<project>/<slug>` to update only a single repository. The latter makes
it easy to make a post-push hook update the database automatically.        