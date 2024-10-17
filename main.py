#!/usr/bin/env python

import urllib.parse
import os
from flask import Flask, render_template, request, redirect
from google.cloud import datastore, storage, vision, error_reporting

app = Flask(__name__)

# 设置环境变量
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/vector/test101-438313.json"
os.environ['CLOUD_STORAGE_BUCKET'] = 'vision-api-gae-proj23-unique'

CLOUD_STORAGE_BUCKET = os.environ.get("CLOUD_STORAGE_BUCKET", "vision-api-gae-proj23-unique")

# 初始化Google Cloud服务客户端
datastore_client = datastore.Client()
storage_client = storage.Client()
vision_client = vision.ImageAnnotatorClient()
bucket = storage_client.get_bucket(CLOUD_STORAGE_BUCKET)

@app.route('/')
def root():
    welcome = "Welcome..!! Choose the category of photos to display"
    return render_template('home.html', welcome=welcome)

@app.route('/photos/<category>')
def photos_cat(category):
    query = datastore_client.query(kind=category)
    photos_category = list(query.fetch())    
    category = category.capitalize()
    return render_template('category.html', photos_category=photos_category, category=category)

@app.route('/photos/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        photo = request.files["file"]
        blob = bucket.blob(photo.filename)
        blob.upload_from_string(photo.read(), content_type=photo.content_type)
        blob.make_public()
        
        image_label = vision_api(blob)
        
        entity = datastore.Entity(key=datastore_client.key(image_label))
        entity.update({
            'Who': request.form['photographer'],
            'Where': request.form['location'],
            'When': request.form['captureddate'],
            'What': blob.public_url,
            'Which': image_label.capitalize()
        })
        datastore_client.put(entity)
        
        return redirect(f'/photos/{image_label}')
    return render_template('upload.html')

def vision_api(blob):
    image_uri = blob.public_url
    image = vision.Image()
    image.source.image_uri = image_uri
    response = vision_client.label_detection(image=image)
    objects = vision_client.object_localization(image=image).localized_object_annotations

    all_labels = [label.description for label in response.label_annotations]

    if "Mammal" in all_labels or "Livestock" in all_labels:
        return "animals"
    elif "Human" in all_labels or "People" in all_labels:
        return "people"
    elif "Flower" in all_labels:
        return "flowers"
    else:
        all_objects = [obj.name for obj in objects]
        if "Person" in all_objects:
            return "people"
        return "others"

@app.route('/photos/<category>/<category_id>/edit', methods=['GET', 'POST'])
def edit(category, category_id):
    id_key = datastore_client.key(category, int(category_id))
    query = datastore_client.query(kind=category)
    query.key_filter(id_key, '=')
    results = list(query.fetch())
    
    if request.method == 'POST':
        photo = request.files.get("file")
        blob_url = results[0]['What']
        blob_name = urllib.parse.unquote(blob_url.split('/')[-1])
        
        if photo:
            blob = bucket.blob(blob_name)
            blob.delete()
            
            new_blob = bucket.blob(photo.filename)
            new_blob.upload_from_string(photo.read(), content_type=photo.content_type)
            new_blob.make_public()
            
            image_label = vision_api(new_blob)
            
            entity = datastore.Entity(key=datastore_client.key(image_label, int(category_id)))
            entity.update({
                'Who': request.form['photographer'],
                'Where': request.form['location'],
                'When': request.form['captureddate'],
                'What': new_blob.public_url,
                'Which': image_label.capitalize()
            })
            
            datastore_client.put(entity)
            if image_label != category:
                datastore_client.delete(id_key)
            return redirect(f'/photos/{image_label}')
        
        # 更新category信息
        entity = datastore.Entity(key=datastore_client.key(category, int(category_id)))
        entity.update({
            'Who': request.form['photographer'],
            'Where': request.form['location'],
            'When': request.form['captureddate'],
            'Which': request.form['category'].capitalize(),
            'What': blob_url
        })
        datastore_client.put(entity)
        return redirect(f'/photos/{category}')
    return render_template('edit.html', results=results)

@app.route('/photos/<category>/<category_id>/delete')
def delete(category, category_id):
    id_key = datastore_client.key(category, int(category_id))
    result = datastore_client.get(id_key)
    
    if result:
        blob_url = result['What']
        blob_name = urllib.parse.unquote(blob_url.split('/')[-1])
        blob = bucket.blob(blob_name)
        blob.delete()
        datastore_client.delete(id_key)
    return redirect(f'/photos/{category}')

@app.errorhandler(500)
def server_error(e):
    errorrep_client = error_reporting.Client()
    errorrep_client.report_exception(http_context=error_reporting.build_flask_context(request))
    return f"An internal error occurred: <pre>{e}</pre> See logs for full stacktrace.", 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
