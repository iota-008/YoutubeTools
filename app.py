from flask import Flask,render_template,request,url_for
from flask.helpers import flash
from flask.json import jsonify
import requests
from requests import sessions
from werkzeug.utils import redirect 
from youtube_transcript_api import YouTubeTranscriptApi
from flask_jsglue import JSGlue
from pytube import YouTube
from flask_cors import CORS, cross_origin


app = Flask(__name__)
# origins=["http://localhost:5000"], 
CORS(app,headers=['Content-Type'], expose_headers=['Access-Control-Allow-Origin'], supports_credentials=True)
jsglue = JSGlue(app)
app.config['CORS_HEADERS'] = 'Content-Type'
app.secret_key = "6969696969"
SAVE_PATH = "C:/"

videos = []

@app.route('/')
def index():
    return render_template('index.html')

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
        return render_template('index.html')

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
        return render_template('index.html')

@app.route('/videoQuality',methods=["GET","POST"])
def videoQuality():
    video_download = videos[0]
    if request.method == 'POST':
        for v in videos:
            if request.form['video'] == v:
                video_download = v
        video_download.download(SAVE_PATH) 
        flash("Video Downloaded Successfully into C Drive")
        return redirect(url_for('index'))
    else:
        flash("Something Went Wrong")
        return render_template('index.html')

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
        return render_template('index.html')
