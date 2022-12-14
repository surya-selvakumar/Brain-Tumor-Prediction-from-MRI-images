import os
import requests
from flask import Flask, flash, request, redirect, url_for, render_template, session, jsonify
from werkzeug.utils import secure_filename
from io import BytesIO
from torch import argmax, load
from torch import device as DEVICE
from torch.cuda import is_available
from torch.nn import Sequential, Linear, SELU, Dropout, LogSigmoid
from PIL import Image
from torchvision.transforms import Compose, ToTensor, Resize
from torchvision.models import resnet50

UPLOAD_FOLDER = './static/images'
ALLOWED_EXTENSIONS = ['png', 'jpg', 'jpeg']

app = Flask(__name__, template_folder='template')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = "m4xpl0it"


LABELS = ['None', 'Meningioma', 'Glioma', 'Pitutary']

device = "cuda" if is_available() else "cpu"

resnet_model = resnet50(pretrained=True)

for param in resnet_model.parameters():
    param.requires_grad = True

n_inputs = resnet_model.fc.in_features
resnet_model.fc = Sequential(Linear(n_inputs, 2048),
                            SELU(),
                            Dropout(p=0.4),
                            Linear(2048, 2048),
                            SELU(),
                            Dropout(p=0.4),
                            Linear(2048, 4),
                            LogSigmoid())

for name, child in resnet_model.named_children():
    for name2, params in child.named_parameters():
        params.requires_grad = True

resnet_model.to(device)
resnet_model.load_state_dict(load('./models/bt_resnet50_model.pt', map_location=DEVICE(device)))
resnet_model.eval()

def preprocess_image(image_bytes):
  transform = Compose([Resize((512, 512)), ToTensor()])
  img = Image.open(BytesIO(image_bytes))
  return transform(img).unsqueeze(0)

def get_prediction(image_bytes):
  tensor = preprocess_image(image_bytes=image_bytes)
  y_hat = resnet_model(tensor.to(device))
  class_id = argmax(y_hat.data, dim=1)
  return str(int(class_id)), LABELS[int(class_id)]

@app.route('/predict', methods=['POST'])
def predict():
  if request.method == 'POST':
    file = request.files['file']
    img_bytes = file.read()
    class_id, class_name = get_prediction(img_bytes)
    return jsonify({'class_id': class_id, 'class_name': class_name})

@app.route('/empty_page')
def empty_page():
    filename = session.get('filename', None)
    os.remove(os.path.join(UPLOAD_FOLDER, filename))
    return redirect(url_for('index'))

@app.route('/pred_page')
def pred_page():
    pred = session.get('pred_label', None)
    f_name = session.get('filename', None)
    return render_template('pred.html', pred=pred, f_name=f_name)

@app.route('/', methods=['POST', 'GET'])
def index():
    try:
        if request.method == 'POST':
            f = request.files['bt_image']
            filename = str(f.filename)

            if filename!='':
                ext = filename.split(".")
                
                if ext[1] in ALLOWED_EXTENSIONS:
                    filename = secure_filename(f.filename)

                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

                    with open(os.path.join(app.config['UPLOAD_FOLDER'], filename),'rb') as img:
                        predicted = requests.post("http://localhost:5000/predict", files={"file": img}).json()

                    session['pred_label'] = predicted['class_name']
                    session['filename'] = filename

                    return redirect(url_for('pred_page'))

    except Exception as e:
        print("Exception\n")
        print(e, '\n')

    return render_template('index.html')

if __name__=="__main__":
    app.run(port=5000)
    