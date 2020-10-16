import urllib.parse
import os
from flask import Flask, render_template, request, redirect
from google.cloud import datastore
from google.cloud import storage
from google.cloud import vision
from google.cloud import error_reporting
app= Flask(__name__)
os.environ['GOOGLE_APPLICATION_CREDENTIALS']=r'Vision-API-GAE-Proj2-4687394a0854.json'
os.environ['CLOUD_STORAGE_BUCKET']='vision-api-gae-proj2'
CLOUD_STORAGE_BUCKET = os.environ.get("CLOUD_STORAGE_BUCKET", "vision-api-gae-proj2")
datastore_client = datastore.Client()
storage_client = storage.Client()
vision_client = vision.ImageAnnotatorClient()
bucket = storage_client.get_bucket(CLOUD_STORAGE_BUCKET)

@app.route('/')
def root():
    welcome = "Welcome..!! Choose the category of photos to display"
    return render_template(
        'home.html', welcome= welcome)

@app.route('/photos/<category>')
def photos_cat(category):
    query = datastore_client.query(kind=category)
    photos_category = query.fetch()
    category=category.capitalize()
    return render_template(
        'category.html', photos_category=photos_category, category=category)

@app.route('/photos/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        photo = request.files["file"]
        blob = bucket.blob(photo.filename)
        blob.upload_from_string(photo.read(), content_type=photo.content_type)
        blob.make_public()
        image_label = vision_api(blob)
        # print("IMAGE_LABEL " + image_label)
        entity = datastore.Entity(key=datastore_client.key(image_label))
        entity.update({
            'Who' : request.form['photographer'],
            'Where' : request.form['location'],
            'When' : request.form['captureddate'],
            'What' : blob.public_url,
            'Which' : image_label.capitalize()
        })
        datastore_client.put(entity)
        return redirect('/photos/'+image_label)
    return render_template('upload.html', photo={})

def vision_api(blob):
    all_labels = []
    image_uri = blob.public_url
    image = vision.Image()
    image.source.image_uri = image_uri
    response = vision_client.label_detection(image=image)
    for label in response.label_annotations:
        # print(label.description, '(%.2f%%)' % (label.score*100.))
        all_labels.append(label.description)
    # print(all_labels)
    image_label = " "
    if  "Mammal" in all_labels:
        image_label = "animals"
    elif "Human" in all_labels or "People" in all_labels:
        image_label = "people"
    elif "Flower" in all_labels:
        image_label = "flowers"
    else:
        image_label = "others"
    return image_label
        
@app.route('/photos/<category>/<category_id>/edit', methods=['GET', 'POST'])
def edit(category, category_id):
    query = datastore_client.query(kind=category)
    id_key = datastore_client.key(category, int(category_id))
    query.key_filter(id_key, '=')
    results = query.fetch()
    if request.method == 'POST':
        if(request.files["file"]):
            photo = request.files["file"]
            for result in results:
                blob_url=result['What']
            blob_name = blob_url[52:]
            blob = bucket.blob(blob_name)
            blob.delete()
            blob = bucket.blob(photo.filename)
            blob.upload_from_string(photo.read(), content_type=photo.content_type)
            blob.make_public()
            image_label = vision_api(blob)
            # print("IMAGE_LABEL " + image_label)
            entity = datastore.Entity(key=datastore_client.key(image_label,int(category_id)))
            entity.update({
                'Who' : request.form['photographer'],
                'Where' : request.form['location'],
                'When' : request.form['captureddate'],
                'What' : blob.public_url,
                'Which' : image_label.capitalize()
            })
            datastore_client.put(entity)
            if(image_label.capitalize() != category):
                datastore_client.delete(id_key)
            return redirect('/photos/'+image_label)
        elif(request.form['category']!=category.capitalize()):
            entity = datastore.Entity(key=datastore_client.key(request.form['category'].lower()))
            entity.update({
                'Who' : request.form['photographer'],
                'Where' : request.form['location'],
                'When' : request.form['captureddate'],
                'Which' : request.form['category'].capitalize(),
                'What' : request.form['uploadedphoto']
            })
            datastore_client.put(entity)
            datastore_client.delete(id_key)
            return redirect('/photos/'+request.form['category'].lower())
        else:
            entity = datastore.Entity(key=datastore_client.key(category,int(category_id)))
            entity.update({
                'Who' : request.form['photographer'],
                'Where' : request.form['location'],
                'When' : request.form['captureddate'],
                'Which' : request.form['category'].capitalize(),
                'What' : request.form['uploadedphoto']
            })
            datastore_client.put(entity)
            return redirect('/photos/'+category)
    return render_template('edit.html', results=results)

@app.route('/photos/<category>/<category_id>/delete')
def delete(category, category_id):
    query = datastore_client.query(kind=category)
    id_key = datastore_client.key(category, int(category_id))
    query.key_filter(id_key, '=')
    results = query.fetch()
    for result in results:
        blob_url=result['What']
    blob_name = blob_url[52:]
    blob_name=urllib.parse.unquote(blob_name)
    blob = bucket.blob(blob_name)
    blob.delete()
    datastore_client.delete(id_key)
    return redirect('/photos/'+category)

@app.errorhandler(500)
def server_error(e):
    errorrep_client = error_reporting.Client()
    errorrep_client.report_exception(
        http_context=error_reporting.build_flask_context(request))
    return """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(e), 500

if __name__ == "__main__":
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host="127.0.0.1", port=8080, debug=True)