_="""
    FACE MASK DETECTION USING TENSORFLOW
        By: Atharva and Osemekhian
"""
print(_)

#====================================Libraries imports================================================
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import re, os, shutil, cv2, glob, math
from tqdm import tqdm
from keras.layers import *
from keras.callbacks import ModelCheckpoint
import tensorflow as tf
import xml.etree.ElementTree as ET
from sklearn.model_selection import train_test_split
from keras.preprocessing.image import ImageDataGenerator
from keras.callbacks import *
from tensorflow import keras
import cv2

batch_size = 16
epochs = 30
img_size= 299
channel= 3
n_classes= 2
LR= 1e-4
random_state= 42
main_path= os.getcwd()

#====================================Helper Functions================================================

input_data_path = '/home/ubuntu/finalproject'+'/images'
annotations_path ='/home/ubuntu/finalproject'+ "/annotations"

# Set the preprocess_input of the pretrained model
preprocess_input = tf.keras.applications.xception.preprocess_input  #xception.preprocess_input


def get_key(value, dictionary):
  for key, val in dictionary.items():
    if value == val:
      return key

def resize(data, label):
    """
    Resize the data into the default input size of the pretrained model

    Parameters
    ----------
    data: the data
    label: the label

    Returns
    ----------
    The resized data and label
    """

    # Resize the data into the default input size of the pretrained model
    data_resized = tf.image.resize(data, input_size)

    return data_resized, label

def merge(dict1, dict2):
    res = {**dict1, **dict2}
    return res



def parse_annotation_object(annotation_object):
    params = {}
    for param in list(annotation_object):
        if param.tag == 'name':
            params['name'] = param.text
        if param.tag == 'bndbox':
            for coord in list(param):
                if coord.tag == 'xmin':
                    params['xmin'] = int(coord.text)
                if coord.tag == 'ymin':
                    params['ymin'] = int(coord.text)
                if coord.tag == 'xmax':
                    params['xmax'] = int(coord.text)
                if coord.tag == 'ymax':
                    params['ymax'] = int(coord.text)
    return params


def parse_annotation(path):
    tree = ET.parse(path)
    root = tree.getroot()
    constants = {}
    objects = [child for child in root if child.tag == 'object']
    for element in tree.iter():
        if element.tag == 'filename':
            constants['file'] = element.text[0: -4]
        if element.tag == 'size':
            for dim in list(element):
                if dim.tag == 'width':
                    constants['width'] = int(dim.text)
                if dim.tag == 'height':
                    constants['height'] = int(dim.text)
                if dim.tag == 'depth':
                    constants['depth'] = int(dim.text)
    object_params = [parse_annotation_object(obj) for obj in objects]
    full_result = [merge(constants, ob) for ob in object_params]
    return full_result

#====================================Data Generation================================================

dataset = [parse_annotation(anno) for anno in glob.glob(annotations_path + '/*.xml')]
full_dataset = sum(dataset, [])
df = pd.DataFrame(full_dataset)
df.rename(columns = {'file':'file_name', 'name':'label'}, inplace = True)
df['file_name'] = [input_data_path + '/' + i + '.png' for i in df['file_name']]
original_df= df.copy(deep=True)
df['label'] = df['label'].map(lambda x: 'with_mask' if x=='mask_weared_incorrect' else x )
print(df.head())

#Encoding Target 'With Mask': 2,'Mask Worn Incorrectly': 1, 'Without Mask': 0
# df['label'] = df['label'].map(lambda x:2 if x=='with_mask' else (1 if x=='mask_weared_incorrect' else 0))

# Turn Target to Categorical type with:
# without_mask-TOP PRIORITY followed by
# 'mask_weared_incorrect'and 'with_mask'
# df['label'] = pd.Categorical(
#     df['label'], categories=['without_mask', 'mask_weared_incorrect', 'with_mask'], ordered=False
# )

# Get labels
labels = df["label"].unique()
print(labels)

# Get train test split
# 20% Test | 80%* Train(20% Validation)
train_df, test_df = train_test_split(df, train_size=0.8, stratify=df['label'])
train_df, valid_df = train_test_split(train_df,train_size=0.8, stratify=train_df['label'])
print(f"Train length:{len(train_df)} \nValidation length:{len(valid_df)} \n"
      f"Test length:{len(test_df)}")

# Image size
img_size = (img_size, img_size) #(35, 35)
input_shape = (img_size, img_size, channel)

# Making data in Tensorflow
train_gen = ImageDataGenerator(rescale=1.0 / 255, horizontal_flip=True, zoom_range=0.1, shear_range=0.2, width_shift_range=0.1,
                               height_shift_range=0.1, rotation_range=4, vertical_flip=False, preprocessing_function=preprocess_input)
valid_gen = ImageDataGenerator(rescale=1.0 / 255, preprocessing_function=preprocess_input)
test_gen = ImageDataGenerator(rescale=1.0 / 255, preprocessing_function=preprocess_input)

train_ds = train_gen.flow_from_dataframe(train_df, x_col='file_name', y_col='label',
                                         target_size=img_size, class_mode="sparse", #class_mode='sparse'
                                         batch_size=batch_size, shuffle=True,
                                         subset='training')

valid_ds = valid_gen.flow_from_dataframe(valid_df, x_col='file_name', y_col='label',
                                         target_size=img_size, class_mode='sparse',
                                         batch_size=batch_size, shuffle=True)

test_ds = test_gen.flow_from_dataframe(test_df, x_col='file_name', y_col='label',
                                         target_size=img_size, class_mode='sparse',
                                         batch_size=batch_size, shuffle=False )

#====================================Pre-Trained Model Xception================================================
# The default input size for the pretrained model input_size = [299, 299]

# Add the pretrained layers
pretrained_model = keras.applications.Xception(include_top=False, weights='imagenet',input_shape=(299, 299, 3))

# Add GlobalAveragePooling2D layer
average_pooling = keras.layers.GlobalAveragePooling2D()(pretrained_model.output)

# Add the output layer
output = keras.layers.Dense(n_classes, activation='sigmoid')(average_pooling) #initially: softmax

# Get the model
model = keras.Model(inputs=pretrained_model.input, outputs=output)

print(model.summary())

#
# For each layer in the pretrained model
for layer in pretrained_model.layers:
    # Freeze the layer
    layer.trainable = False


#====================================CallBacks================================================
# -Using Performance scheduling to tune the learning rate
# -Using early stopping to handle overfitting
# ModelCheckpoint callback to_save_the_model

model_checkpoint_cb = keras.callbacks.ModelCheckpoint(filepath=main_path + '/model_xception_facemask.h5',
                                                      save_best_only=True,
                                                      save_weights_only=False)
# EarlyStopping callback
early_stopping_cb = keras.callbacks.EarlyStopping(patience=3,
                                                  restore_best_weights=True)

# ReduceLROnPlateau callback #Performance Scheduling
reduce_lr_on_plateau_cb = keras.callbacks.ReduceLROnPlateau(factor=0.1,
                                                            patience=2)

#====================================Compile Model================================================
model.compile(optimizer=keras.optimizers.Adam(learning_rate=LR),# or Adam
              loss='sparse_categorical_crossentropy',
              metrics=['accuracy'])

#====================================Initial Training================================================
# Train, evaluate and save the best model
history = model.fit(train_ds,
                    epochs=2,
                    validation_data=valid_ds,
                    callbacks=[model_checkpoint_cb,
                               early_stopping_cb,
                               reduce_lr_on_plateau_cb])

# Create a figure
pd.DataFrame(history.history).plot(figsize=(8, 5))

# Save and show the figure
plt.tight_layout()
plt.legend(loc='center')
plt.title("Learning Curve")
plt.xlabel('Epoch')
plt.tight_layout()
plt.show()

# Unfreezing the  Pre-Trained layers (132)
for layer in pretrained_model.layers:
    # Unfreeze the layer
    layer.trainable = True

# Here we use a lower learning rate (by a factor of 10) of Adam optimizer,
# so that it is less likely to compromise the pretrained weights.

# Compile the model
model.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-5),
              loss='sparse_categorical_crossentropy',
              metrics=['accuracy'])

# Train, evaluate and save the best model
history = model.fit(train_ds,
                    epochs=10,
                    validation_data=valid_ds,
                    callbacks=[model_checkpoint_cb,
                               early_stopping_cb,
                               reduce_lr_on_plateau_cb])

# Create a figure
pd.DataFrame(history.history).plot(figsize=(8, 5))

# Save and show the figure
plt.tight_layout()
plt.legend(loc='center')
plt.title("Learning Curve")
plt.xlabel('Epoch')
plt.tight_layout()
plt.show()



#===================================================
# Testing:
class_dict=test_ds.class_indices

# Load the saved model
model.load_weights(filepath=main_path + os.path.sep +'model_xception_facemask.h5')
loss, accuracy= model.evaluate(test_ds)
pred= model.predict(test_ds)


# My Test
def imgs_to_df(path, images_list):
    dat = []
    for i in range(len(images_list)):
        dat.append(path + images_list[i])
    test_imgs = pd.DataFrame(data=dat, columns=['images'])

    return test_imgs


def facemask(image_df,column_name, image_generator,model,get_key, class_dict, batch_size=16):
    ''':image_df : Should be in Dataframe
    :column_name : name of image column in string
    :image_generator : Tensorflow image generator with preprocessing function
    :model : saved model
    :get_key : function to check np.argmax value then return key
    :class_dict : dictionary for classes
    Image size is (299,299) for Xception Model
    '''
    tensor= image_generator.flow_from_dataframe(image_df, x_col=column_name,
                                         target_size=img_size, class_mode=None,
                                         batch_size=batch_size, shuffle=False)
    new_pred = model.predict(tensor)
    prediction = []
    for i in range(len(new_pred)):
        prediction.append(np.argmax(new_pred[i]))
    pred_df = pd.DataFrame(prediction, columns=['label'])
    pred_df.label = pred_df.label.map(lambda x: get_key(x, class_dict))

    return pred_df.label

new_path= main_path + '/test/'
imgs=os.listdir(new_path)
test_imgs= imgs_to_df(path=new_path,images_list=imgs)
new_predictions = facemask(test_imgs,'images',test_gen,model,get_key,class_dict)
print(new_predictions)

#Try Plots
labz= ['With Mask','without Mask','without Mask','With Mask']
idx=1
for i in range(4):
    plt.subplot(2, 2, idx)
    pic = cv2.imread(test_imgs.images.values[i])
    plt.imshow(pic)
    plt.title(f"Label:{labz[i]}|Pred:{new_predictions[i]} ",fontdict={'size':10})
    idx +=1

plt.tight_layout()
plt.show()
