#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from sys import exit
import psycopg2
import psycopg2.extras
import markdown
import os.path
import re
import torndb
import tornado.auth
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import unicodedata

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)
define("pgsql_host", default="127.0.0.1:5432", help="blog database host")
define("pgsql_database", default="rocketui", help="blog database name")
define("pgsql_user", default="rocketui", help="blog database user")
define("pgsql_password", default="rocketui", help="blog database password")


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", HomeHandler),
            (r"/archive", ArchiveHandler),
            (r"/feed", FeedHandler),
            (r"/entry", EntryHandler),
#            (r"/entry/([0-9]+)", EntryHandler),
            (r"/compose", ComposeHandler),
            (r"/auth/login", AuthLoginHandler),
            (r"/auth/logout", AuthLogoutHandler),
        ]
        settings = dict(
            blog_title=u"Tornado Blog",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            ui_modules={"Entry": EntryModule},
            xsrf_cookies=True,
            cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
            login_url="/auth/login",
            debug=True,
        )
        tornado.web.Application.__init__(self, handlers, **settings)

        # Have one global connection to the blog DB across all handlers
        try:
          self.db_con = psycopg2.connect(database=options.pgsql_database, user=options.pgsql_user, password=options.pgsql_password, host=options.pgsql_host)
          self.db_cur = self.db_con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        except psycopg2.DatabaseError, e:
          print 'Error: %s' % e
          exit()


class BaseHandler(tornado.web.RequestHandler):
    @property
    def db(self):
        return self.application.db_cur
    def db_con(self):
        return self.application.db_con
    def get_current_user(self):
        user_id = self.get_secure_cookie("blogdemo_user")
        if not user_id: return None
        return {'name':'tony','email':'teriyakichild@gmail.com','id':'1'}


class HomeHandler(BaseHandler):
    def get(self):
        self.db.execute("SELECT * FROM launches;")
        entries = self.db.fetchall()
        if not entries:
            self.redirect("/compose")
            return
        self.render("home.html", entries=entries)


class EntryHandler(BaseHandler):
    def get(self):
        id = self.get_argument("id",None)
        self.db.execute("SELECT * FROM launches WHERE id = %s" % id)
        entry = self.db.fetchone()
        print entry
        if not entry: raise tornado.web.HTTPError(404)
        self.render("entry.html", entry=entry)


class ArchiveHandler(BaseHandler):
    def get(self):
        self.db.execute("SELECT * FROM launches;")
        entries = self.db.fetchall()
        self.render("archive.html", entries=entries)


class FeedHandler(BaseHandler):
    def get(self):
        self.db.execute("SELECT * FROM launches;")
        entries = self.db.fetchall()
        self.set_header("Content-Type", "application/atom+xml")
        self.render("feed.xml", entries=entries)


class ComposeHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        id = self.get_argument("id", None)
        entry = None
        if id:
            self.db.execute("SELECT * FROM launches WHERE id = %s" % int(id))
            entry = self.db.fetchone()
            print entry
        self.render("compose.html", entry=entry)

    @tornado.web.authenticated
    def post(self):
        id = self.get_argument("id", None)
        location = self.get_argument("location")
        if id:
            self.db.execute("SELECT * FROM launches WHERE id = %s" % int(id))
            entry = self.db.fetchone()
            if not entry: raise tornado.web.HTTPError(404)
            id = entry['id']
            self.db.execute("UPDATE launches SET location = '%s' WHERE id = %s" % (location,int(id)))
            self.db_con().commit()
        else:
            self.db.execute("INSERT INTO launches (location,date) VALUES ('%s',now()) RETURNING id" % str(location))
            self.db_con().commit()
            id = self.db.fetchone()[0]
        self.redirect("/entry?id=" + str(id))


class AuthLoginHandler(BaseHandler, tornado.auth.GoogleMixin):
    @tornado.web.asynchronous
    def get(self):
        if self.get_argument("openid.mode", None):
            self.get_authenticated_user(self.async_callback(self._on_auth))
            return
        self.authenticate_redirect()

    def _on_auth(self, user):
        if not user:
            raise tornado.web.HTTPError(500, "Google auth failed")
        author = self.db.get("SELECT * FROM authors WHERE email = %s",
                             user["email"])
        if not author:
            # Auto-create first author
            any_author = self.db.get("SELECT * FROM authors LIMIT 1")
            if not any_author:
                author_id = self.db.execute(
                    "INSERT INTO authors (email,name) VALUES (%s,%s)",
                    user["email"], user["name"])
            else:
                self.redirect("/")
                return
        else:
            author_id = author["id"]
        self.set_secure_cookie("blogdemo_user", str(author_id))
        self.redirect(self.get_argument("next", "/"))


class AuthLogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("blogdemo_user")
        self.redirect(self.get_argument("next", "/"))


class EntryModule(tornado.web.UIModule):
    def render(self, entry):
        return self.render_string("modules/entry.html", entry=entry)


def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()
