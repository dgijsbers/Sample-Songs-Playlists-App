__author__ = "Jackie Cohen (jczetta)"
# An application about recording favorite songs & info

import os
from flask import Flask, render_template, session, redirect, request, url_for, flash
from flask_script import Manager, Shell
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField, PasswordField, BooleanField, SelectMultipleField, ValidationError
from wtforms.validators import Required, Length, Email, Regexp, EqualTo
from flask_sqlalchemy import SQLAlchemy
import random
from flask_migrate import Migrate, MigrateCommand

# Imports for email from app
from flask_mail import Mail, Message
from threading import Thread
from werkzeug import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Imports for login management
from flask_login import LoginManager, login_required, logout_user, login_user, UserMixin, current_user

# Configure base directory of app
basedir = os.path.abspath(os.path.dirname(__file__))

# Application configurations
app = Flask(__name__)
app.static_folder = 'static'
app.config['SECRET_KEY'] = 'hardtoguessstring'
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get('DATABASE_URL') or "postgresql://localhost/songs_and_playlists"  # TODO: decide what your new database name will be, and create it in postgresql, before running this new application
# Lines for db setup so it will work as expected
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Set up email config stuff
app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
app.config['MAIL_PORT'] = 587 #default
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME') # TODO export to your environs -- may want a new account just for this. It's expecting gmail, not umich
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_SUBJECT_PREFIX'] = '[Songs App]'
app.config['MAIL_SENDER'] = 'Admin <>' # TODO fill in email
app.config['ADMIN'] = os.environ.get('ADMIN') or "admin@example.com" # If Admin in environ variable / in prod or this fake email
app.config['HEROKU_ON'] = os.environ.get('HEROKU')

# Set up Flask debug and necessary additions to app
manager = Manager(app)
db = SQLAlchemy(app) # For database use
migrate = Migrate(app, db) # For database use/updating
manager.add_command('db', MigrateCommand) # Add migrate command to manager
mail = Mail(app) # For email sending

# Login configurations setup
login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.init_app(app) # set up login manager

## Set up Shell context so it's easy to use the shell to debug
# Define function
def make_shell_context():
    return dict( app=app, db=db) #Song=Song, Artist=Artist, Album=Album, User=User,Playlist=Playlist)
# Add function use to manager
manager.add_command("shell", Shell(make_context=make_shell_context))

## NOTE ON MIGRATION SETUP
## You will get the following message when running command to create migration folder, e.g.:
## python main_app.py db init
## -->
# Please edit configuration/connection/logging settings in ' ... migrations/alembic.ini' before proceeding
## This is what you are supposed to see!

#########
######### Everything above this line is important/useful setup, not mostly application-specific problem-solving.
#########

##### Functions to send email #####

def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

def send_email(to, subject, template, **kwargs): # kwargs = 'keyword arguments', this syntax means to unpack any keyword arguments into the function in the invocation...
    msg = Message(app.config['MAIL_SUBJECT_PREFIX'] + ' ' + subject,
                  sender=app.config['MAIL_SENDER'], recipients=[to])
    msg.body = render_template(template + '.txt', **kwargs)
    msg.html = render_template(template + '.html', **kwargs)
    thr = Thread(target=send_async_email, args=[app, msg]) # using the async email to make sure the email sending doesn't take up all the "app energy" -- the main thread -- at once
    thr.start()
    return thr # The thread being returned
    # However, if your app sends a LOT of email, it'll be better to set up some additional "queuing" software libraries to handle it. But we don't need to do that yet. Not quite enough users!


##### Set up Models #####

# Set up association Table between artists and albums
collections = db.Table('collections',db.Column('album_id',db.Integer, db.ForeignKey('albums.id')),db.Column('artist_id',db.Integer, db.ForeignKey('artists.id')))

# Set up association Table between songs and playlists
on_playlist = db.Table('on_playlist',db.Column('user_id', db.Integer, db.ForeignKey('songs.id')),db.Column('playlist_id',db.Integer, db.ForeignKey('playlists.id')))

# Special model for users to log in
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, index=True)
    email = db.Column(db.String(64), unique=True, index=True)
    playlists = db.relationship('Playlist', backref='User')
    password_hash = db.Column(db.String(128))

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)


# Other models

class Playlist(db.Model):
    __tablename__ = "playlists"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    songs = db.relationship('Song',secondary=on_playlist,backref=db.backref('playlists',lazy='dynamic'),lazy='dynamic')

class Album(db.Model):
    __tablename__ = "albums"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    artists = db.relationship('Artist',secondary=collections,backref=db.backref('albums',lazy='dynamic'),lazy='dynamic')
    songs = db.relationship('Song',backref='Album')


class Artist(db.Model):
    __tablename__ = "artists"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    songs = db.relationship('Song',backref='Artist')

    def __repr__(self):
        return "{} (ID: {})".format(self.name,self.id)

class Song(db.Model):
    __tablename__ = "songs"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(64),unique=True) # Only unique title songs
    album_id = db.Column(db.Integer, db.ForeignKey("albums.id"))
    artist_id = db.Column(db.Integer, db.ForeignKey("artists.id"))
    genre = db.Column(db.String(64))


    def __repr__(self):
        return "{} by {} | {}".format(self.title,self.artist_id, self.genre)

# ## DB load functions
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id)) # returns User object or None


##### Set up Forms #####

class RegistrationForm(FlaskForm):
    email = StringField('Email:', validators=[Required(),Length(1,64),Email()])
    username = StringField('Username:',validators=[Required(),Length(1,64),Regexp('^[A-Za-z][A-Za-z0-9_.]*$',0,'Usernames must have only letters, numbers, dots or underscores')])
    password = PasswordField('Password:',validators=[Required(),EqualTo('password2',message="Passwords must match")])
    password2 = PasswordField("Confirm Password:",validators=[Required()])
    submit = SubmitField('Register User')

    #Additional checking methods for the form
    def validate_email(self,field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('Email already registered.')

    def validate_username(self,field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Username already taken')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[Required(), Length(1,64), Email()])
    password = PasswordField('Password', validators=[Required()])
    remember_me = BooleanField('Keep me logged in')
    submit = SubmitField('Log In')

class PlaylistCreateForm(FlaskForm):
    songs = Song.query.all()
    song_titles_val_descr = [(s.title,s.title) for s in songs]
    name = StringField('Playlist Name',validators=[Required()])
    song_picks = SelectMultipleField('Songs to include',choices=song_titles_val_descr)
    submit = SubmitField("Create Playlist")


class SongForm(FlaskForm):
    song = StringField("What is the title of your favorite song?", validators=[Required()])
    artist = StringField("What is the name of the artist who performs it?",validators=[Required()])
    genre = StringField("What is the genre of that song?", validators
        =[Required()])
    album = StringField("What is the album this song is on?", validators
        =[Required()])
    submit = SubmitField('Submit')

class UploadForm(FlaskForm):
    file = FileField()

##### Helper functions

### For database additions / get_or_create functions

def get_song_by_name(song_name):
    """returns song or None"""
    s = Song.query.filter_by(title=song_name).first()
    return s

def get_or_create_artist(db_session,artist_name):
    artist = db_session.query(Artist).filter_by(name=artist_name).first()
    if artist:
        return artist
    else:
        artist = Artist(name=artist_name)
        db_session.add(artist)
        db_session.commit()
        return artist

def get_or_create_album(db_session, album_name, artists_list=[]):
    album = db_session.query(Album).filter_by(name=album_name).first() # by name filtering for album
    if album:
        return album
    else:
        album = Album(name=album_name)
        for artist in artists_list:
            artist = get_or_create_artist(db_session,artist)
            album.artists.append(artist)
        db_session.add(album)
        db_session.commit()
    return album

def get_or_create_song(db_session, song_title, song_artist, song_album, song_genre):
    song = db_session.query(Song).filter_by(title=song_title).first()
    if song:
        return song
    else:
        artist = get_or_create_artist(db_session, song_artist)
        album = get_or_create_album(db_session, song_album, artists_list=[song_artist]) # list of one song artist each time -- check out get_or_create_album and get_or_create_artist!
        song = Song(title=song_title,genre=song_genre,artist_id=artist.id)
        db_session.add(song)
        db_session.commit()
        return song

def get_or_create_playlist(db_session, name,song_list,current_user):
    playlist = db_session.query(Playlist).filter_by(name=name,user_id=current_user.id).first()
    if playlist:
        return playlist
    else:
        p = Playlist(name=name,user_id=current_user.id,songs=[])
        for song in song_list:
            p.songs.append(song)
        db_session.add(p)
        db_session.commit()
        return p




##### Set up Controllers (view functions) #####

## Error handling routes
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

## Login routes
@app.route('/login',methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is not None and user.verify_password(form.password.data):
            login_user(user, form.remember_me.data)
            return redirect(request.args.get('next') or url_for('index'))
        flash('Invalid username or password.')
    return render_template('login.html',form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out')
    return redirect(url_for('index'))

@app.route('/register',methods=["GET","POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(email=form.email.data,username=form.username.data,password=form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('You can now log in!')
        return redirect(url_for('login'))
    return render_template('register.html',form=form)



@app.route('/secret')
@login_required
def secret():
    return "Only authenticated users can do this! Try to log in or contact the site admin."

## Main routes

@app.route('/', methods=['GET', 'POST'])
def index():
    songs = Song.query.all()
    num_songs = len(songs)
    form = SongForm()
    if form.validate_on_submit():
        if db.session.query(Song).filter_by(title=form.song.data).first(): # If there's already a song with that title, though...nvm, can't. Gotta add something like "(covered by..) or whatever"
            flash("You've already saved a song with that title!")
        else:
            get_or_create_song(db.session,form.song.data, form.artist.data, form.album.data, form.genre.data)
            if app.config['ADMIN']:
                #send_email(app.config['ADMIN'], 'New Song','mail/new_song', song=form.song.data)
                flash("Email would be sent to {} if email secure server were set up".format(app.config['ADMIN']))
        return redirect(url_for('see_all'))
    return render_template('index.html', form=form,num_songs=num_songs)

@app.route('/all_songs')
def see_all():
    all_songs = [] # To be tuple list of title, genre
    songs = Song.query.all()
    for s in songs:
        artist = Artist.query.filter_by(id=s.artist_id).first()
        all_songs.append((s.title,artist.name, s.genre))
    return render_template('all_songs.html',all_songs=all_songs)

@app.route('/all_artists')
def see_all_artists():
    artists = Artist.query.all()
    names = [(a.name, len(Song.query.filter_by(artist_id=a.id).all())) for a in artists]
    return render_template('all_artists.html',artist_names=names)

@app.route('/playlists')
@login_required
def playlists(methods=["GET","POST"]):
    lists = Playlist.query.filter_by(user_id=current_user.id).all()
    names_urls = [(p.name, url_for('playlist',id=p.id)) for p in lists]
    return render_template('all_playlists.html',names_urls=names_urls)

@app.route('/playlist/<id>')
def playlist(id):
    p = Playlist.query.filter_by(id=id).first() # Note the .first() -- easy to forget what type the result of a query is!
    name = p.name
    songs = [s.title for s in p.songs]
    return render_template('playlist.html',name=name,songs=songs)


@app.route('/create_playlist',methods=["GET","POST"])
@login_required
def create_playlist():
    form = PlaylistCreateForm()
    if form.validate_on_submit():
        song_titles = form.song_picks.data # list?
        song_objects = [get_song_by_name(name) for name in song_titles] # list of Song objects from queries??
        # import code; code.interact(local=dict(globals(), **locals()))
        get_or_create_playlist(db.session,current_user=current_user,name=form.name.data,song_list=song_objects) # How to access user, here and elsewhere TODO
        return redirect(url_for('playlists'))
    return render_template('create_playlist.html',form=form)




@app.route('/group1')
def group1():
    all_albums = Album.query.all()
    return render_template('all_albums.html',albums=all_albums)

@app.route('/group2')
def group2():
    songs_Rock = Songs.query.filter_by(genre="Rock")
    return render_template('rock_songs.html',rock_songs=songs_Rock)

@app.route('/group3')
def group3():
    artists_albums = []
    for al in Album.query.all():
        for artist in al.artists:
            artists_albums.append(al.name, artist.name)
    return render_template('artist_albums.html',artists_and_albums=artists_albums)

@app.route('/group4')
def group4():
    songs_shakira = Song.query.filter_by(artist_id=get_or_create_artist("Shakira").id)
    names = [s.name for s in songs_shakira]
    return render_template('shakira_songs.html',song_names=names)

@app.route('/group5')
def group5():
    artist_beethoven = Artist.query.filter_by(name="Beethoven") # If there's no such artist, what's gonna happen? Try and find out! -- What might you want to change in the template to handle different situations?
    songs_beethoven = Song.query.filter_by(artist_id=artist_beethoven.id)
    return render_template('beethoven_songs.html',songs_beethoven=songs_beethoven)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        filename = secure_filename(form.file.data.filename)
        form.file.data.save('static/imgs/' + filename) # Get file data due to the way the form specifies it -- FileField is special
        # Then can save it wherever you direct it to be saved
        # Can also save File Blobs to database --
        return redirect(url_for('upload'))

    return render_template('upload.html', form=form)

# ...static/imgs/whatevername.jpg
# .../static/imgs/yosemite.jpg
@app.route('/viewimage')
def random_image(): # Uploaded 1, but more won't stay -- for now
    names = os.listdir(os.path.join(app.static_folder, 'imgs'))
    img_url = url_for('static', filename=os.path.join('imgs', random.choice(names)))
    return render_template('random_image.html', img_url=img_url)

@app.route('/all_images')
def all_images():
    names = os.listdir(os.path.join(app.static_folder, 'imgs'))
    img_urls = []
    for name in names:
        img_url = url_for('static', filename=os.path.join('imgs', name))
        img_urls.append(img_url)
    return render_template('all_images.html',img_urls=img_urls)

if __name__ == '__main__':
    db.create_all()
    manager.run() # NEW: run with this: python main_app.py runserver
#     # Also provides more tools for debugging
