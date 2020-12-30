import os
from os import path
from flask import Flask,render_template,request,url_for
from flask import flash, send_from_directory
from flask.helpers import make_response
from flask.json import jsonify
from flask import Response
from werkzeug.utils import redirect 
from youtube_transcript_api import YouTubeTranscriptApi
from flask_jsglue import JSGlue
from pytube import YouTube
from flask_cors import CORS, cross_origin
from flask_talisman import Talisman
from pathlib import Path
from flask_sitemap import Sitemap

app = Flask(__name__)
ext = Sitemap(app=app)
Talisman(app, content_security_policy=None,force_https=True)

# origins=["http://localhost:5000"], 

CORS(app,headers=['Content-Type'], expose_headers=['Access-Control-Allow-Origin'], supports_credentials=True)
jsglue = JSGlue(app)
app.config['CORS_HEADERS'] = 'Content-Type'
app.secret_key = "6969696969"

SAVE_PATH = str(os.path.join(Path.home(), "Downloads"))

videos = []

@app.route('/')
def index():
    return render_template('index.html')

# @ext.register_generator
# def index():
#     # Not needed if you set SITEMAP_INCLUDE_RULES_WITHOUT_PARAMS=True
#     yield 'index', {}
    
app.errorhandler(404)
def page_not_found(e):
    return render_template('page_not_found.html'),404
    
@app.route('/gettext',methods=["GET","POST"])
def gettext():
    if request.method == 'POST':
        url = request.form['url']
        code = url[-11:]
        srt = YouTubeTranscriptApi.get_transcript(code)
    
        with open('static/data.txt','w') as f:
            for i in srt:
                f.writelines(i['text'] + "\n")

        return render_template('transcript.html')
    
    else:
        flash("Something Went Wrong")
        # return render_template('index.html')
        return redirect(url_for('index'),code=301)

@app.route('/download',methods=["GET","POST"])
def download():
    if request.method == 'POST':
        global videos
        url = request.form['url']
        yt = YouTube(url)
        videos = yt.streams.filter(progressive=True).all()
        print(videos)
        return render_template('download.html',videos=videos)
    else:
        flash("Something Went Wrong")
        return redirect(url_for('index'),code=301)

@app.route('/videoQuality',methods=["GET","POST"])
def videoQuality():
    video_download = videos[0]
    if request.method == 'POST':
        for v in videos:
            if request.form['video'] == v:
                video_download = v
        video_download.download(SAVE_PATH) 
        flash("Video Downloaded Successfully")
        return redirect(url_for('index'))
    else:
        flash("Something Went Wrong")
        return redirect(url_for('index'),code=301)

@app.route('/thumbnail',methods=["POST","GET"])
@cross_origin()
def thumbnail():
    if request.method == 'POST':
        url = request.form['url']
        MyVideo = YouTube(url)
        thumbnail_url = MyVideo.thumbnail_url
        return render_template('thumbnail.html',url=thumbnail_url)
    else:
        flash("Something Went Wrong")
        return redirect(url_for('index'),code=301)

@app.route('/robots.txt')
@app.route('/sitemap.xml')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])
