[app]
title = OMR Scanner
package.name = omrscanner
package.domain = org.ashit
source.dir = .
source.include_exts = py,png,jpg,html,css,js
version = 0.1
android.minapi = 24
android.ndk = 23b
android.ndk_api = 24
# IMPORTANT: Flask is the requirement here
requirements = python3,flask,opencv-python,numpy,werkzeug,jinja2,itsdangerous,click,hostpython3

android.blacklist_requirements = wsgiref
android.accept_sdk_license = True

# Add this line below your requirements
android.recipes = opencv,numpy,flask
# Add this to tell the builder to ignore the broken wsgiref package


orientation = portrait
fullscreen = 0
android.permissions = CAMERA, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# This tells Buildozer to use a WebView to show your Flask app
android.bootstrap = webview
android.entrypoint_port = 7860
# Forces buildozer to use the most recent fixes for Python 3.11
p4a.branch = develop
