[app]
title = OMR Scanner
package.name = omrscanner
package.domain = org.ashit
source.dir = .
source.include_exts = py,png,jpg,html,css,js
version = 0.1

# IMPORTANT: Flask is the requirement here
requirements = python3,flask,opencv-python,numpy,werkzeug,jinja2,itsdangerous,click
# Add this line below your requirements
android.recipes = opencv,numpy,flask
# Add this to tell the builder to ignore the broken wsgiref package
android.blacklist_requirements = wsgiref


orientation = portrait
fullscreen = 0
android.permissions = CAMERA, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# This tells Buildozer to use a WebView to show your Flask app
android.bootstrap = webview
android.entrypoint_port = 7860
