
#-----------------------------------------------------------------
#-----------------------------------------------------------------
import urllib.request
import tensorflow as tf
import numpy as np
from tqdm import tqdm
import os
import subprocess
import zipfile
import re

import requests
import zipfile
import io

import tensorflow as tf
from tqdm import tqdm
import numpy as np

from keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences

from numpy import array
import time
#-----------------------------------------------------------------
#-----------------------------------------------------------------
class BahdanauAttention(tf.keras.Model):
    def __init__(self, units):
        super(BahdanauAttention, self).__init__()
        self.W1 = tf.keras.layers.Dense(units)
        self.W2 = tf.keras.layers.Dense(units)
        self.V = tf.keras.layers.Dense(1)

    def call(self, features, hidden):
        hidden_with_time_axis = tf.expand_dims(hidden, 1)
        # attention_hidden_layer shape == (batch_size, 64, units)
        attention_hidden_layer = (tf.nn.tanh(self.W1(features) +
                                                self.W2(hidden_with_time_axis)))
        # score shape == (batch_size, 64, 1)
        # This gives you an unnormalized score for each image feature.
        score = self.V(attention_hidden_layer)

        # attention_weights shape == (batch_size, 64, 1)
        attention_weights = tf.nn.softmax(score, axis=1)

        # context_vector shape after sum == (batch_size, hidden_size)
        context_vector = attention_weights * features
        context_vector = tf.reduce_sum(context_vector, axis=1)

        return context_vector, attention_weights
#-----------------------------------------------------------------
#-----------------------------------------------------------------
class CNN_Encoder(tf.keras.Model):
    # Since you have already extracted the features and dumped it
    # This encoder passes those features through a Fully connected layer
    def __init__(self, embedding_dim):
        super(CNN_Encoder, self).__init__()
        # shape after fc == (batch_size, 64, embedding_dim)
        self.fc = tf.keras.layers.Dense(embedding_dim)

    def call(self, x):
        x = self.fc(x)
        x = tf.nn.relu(x)
        return x
#-----------------------------------------------------------------
#-----------------------------------------------------------------
class RNN_Decoder(tf.keras.Model):
    def __init__(self, embedding_dim, units, vocab_size):
        super(RNN_Decoder, self).__init__()
        self.units = units

        self.embedding = tf.keras.layers.Embedding(vocab_size, embedding_dim)
        self.gru = tf.keras.layers.GRU(self.units,
                                          return_sequences=True,
                                          return_state=True,
                                          recurrent_initializer='glorot_uniform')
        self.fc1 = tf.keras.layers.Dense(self.units)
        self.fc2 = tf.keras.layers.Dense(vocab_size)

        self.attention = BahdanauAttention(self.units)

    def call(self, x, features, hidden):
        # defining attention as a separate model
        context_vector, attention_weights = self.attention(features, hidden)

        # x shape after passing through embedding == (batch_size, 1, embedding_dim)
        x = self.embedding(x)

        # x shape after concatenation == (batch_size, 1, embedding_dim + hidden_size)
        x = tf.concat([tf.expand_dims(context_vector, 1), x], axis=-1)

        # passing the concatenated vector to the GRU
        output, state = self.gru(x)

        # shape == (batch_size, max_length, hidden_size)
        x = self.fc1(output)

        # x shape == (batch_size * max_length, hidden_size)
        x = tf.reshape(x, (-1, x.shape[2]))

        # output shape == (batch_size * max_length, vocab)
        x = self.fc2(x)

        return x, state, attention_weights

    def reset_state(self, batch_size):
        return tf.zeros((batch_size, self.units))

#-----------------------------------------------------------------
#-----------------------------------------------------------------

class ImageCaptioning():
    def __init__(self):
        self.tokenizer = Tokenizer()
        self.image_features_extract_model=None

            
    def load_captions(self, zip_file_path,file_to_access):
        # Extract the file from the zip file
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            with zip_ref.open(file_to_access) as file:
                content = file.read()
                
                return(content)



    def captions_dict (self, text):
        dict = {}
        ## Converting Bytes to string
        text = text.decode('utf-8')
        # Make a List of each line in the file
        lines = text.split ('\n') 
        for line in lines:
            # Split into the <image_data> and <caption>
            line_split = line.split ('\t')
            if (len(line_split) != 2):
                # Added this check because dataset contains some blank lines
                continue
            else:
                image_data, caption = line_split
            # Split into <image_file> and <caption_idx>
            image_file, caption_idx = image_data.split ('#')
            # Split the <image_file> into <image_name>.jpg
            image_name = image_file.split ('.')[0]
            # If this is the first caption for this image, create a new list for that
            # image and add the caption to it. Otherwise append the caption to the 
            # existing list
            if (int(caption_idx) == 0):
                dict [image_name] = [caption]
            else:
                dict [image_name].append (caption)
        
        return (dict)
      
    def subset_image_name (self, train_img_txt):
        data = []
        ## Converting Bytes to string
        train_img_txt = train_img_txt.decode('utf-8')
        # Make a List of each line in the file
        lines = train_img_txt.split ('\n')
        for line in lines:
            # skip empty lines
            if (len(line) < 1):
                continue
            # Each line is the <image_file>
            # Split the <image_file> into <image_name>.jpg
            image_name = line.split ('.')[0]
            # Add the <image_name> to the list
            data.append (image_name)

        return (set(data))
    
    def captions_clean (self, image_dict):
        print_count=0
        # <key> is the image_name, which can be ignored
        for key, captions in image_dict.items():
            # Loop through each caption for this image
            for i, caption in enumerate (captions):
                # Convert the caption to lowercase, and then remove all special characters from it
                caption_nopunct = re.sub(r"[^a-zA-Z0-9]+", ' ', caption.lower())
                # Split the caption into separate words, and collect all words which are more than 
                # one character and which contain only alphabets (ie. discard words with mixed alpha-numerics)
                clean_words = [word for word in caption_nopunct.split() if ((len(word) > 1) and (word.isalpha()))]
                # Join those words into a string
                caption_new = ' '.join(clean_words)
                if print_count<=10:
                    print("\t Old caption:",captions[i])
                        
                # Replace the old caption in the captions list with this new cleaned caption
                captions[i] = caption_new
                if print_count<=10:
                    print("\t New caption:",captions[i])
                        
                print_count += 1

    def load_image(self,image_path):
        img = tf.io.read_file(image_path)
            
        print("\t Decoding the image with 3 color channel")
        img = tf.image.decode_jpeg(img, channels=3)
            
        print("\t Resizing the image to (299, 299)")
        img = tf.image.resize(img, (299, 299))
            
        print("\t Pre built pre processing of Inception V3")
        img = tf.keras.applications.inception_v3.preprocess_input(img)
        return img, image_path

    def process_image_dataset(self,image_dir, training_image_names):
        print("Initializing Inception V3 model without the top classification layers")
        image_model = tf.keras.applications.InceptionV3(include_top=False, weights='imagenet')
            
        print("Retrieving the input tensor 'new_input' and the output tensor of the last layer 'hidden_layer'")
        new_input = image_model.input
        hidden_layer = image_model.layers[-1].output
            
        print("Creating new model using the created input and output")
        self.image_features_extract_model = tf.keras.Model(new_input, hidden_layer)
            
        print("Creating training image path")
        training_image_paths = [image_dir +'/'+ name + '.jpg' for name in training_image_names]
        encode_train = sorted(set(training_image_paths))
            
        print("Creates a TensorFlow dataset, image_dataset, from the sorted training image paths")
        image_dataset = tf.data.Dataset.from_tensor_slices(encode_train)
            
        print("Pre-processing each image data:")
        image_dataset = image_dataset.map(self.load_image, num_parallel_calls=tf.data.experimental.AUTOTUNE).batch(16)

        print("Preparing the preprocessed images in groups of 16 in batches")
        print("Extracting image features on the batch of images")
        print("Reshaping extracted features")
        print("Saving the features as Numpy file")

        for img, path in tqdm(image_dataset):
            batch_features = self.image_features_extract_model(img)
                  
            batch_features = tf.reshape(batch_features, (batch_features.shape[0], -1, batch_features.shape[3]))
                  
            for bf, p in zip(batch_features, path):
                path_of_feature = p.numpy().decode("utf-8")
                np.save(path_of_feature, bf.numpy())


    def add_token (self,captions):
        for i, caption in enumerate (captions):
            captions[i] = 'startseq ' + caption + ' endseq'
            
        return (captions)

      #--------------------------------------------------
    def subset_data_dict (self,image_dict, image_names):
        dict = { image_name:self.add_token(captions) for image_name,captions in image_dict.items() if image_name in image_names}
        return (dict)


      #--------------------------------------------------
    def all_captions (self,data_dict):
        return ([caption for key, captions in data_dict.items() for caption in captions])


      #--------------------------------------------------
    def max_caption_length(self,captions):
        return max(len(caption.split()) for caption in captions)

    def create_tokenizer(self,data_dict):
        captions = self.all_captions(data_dict)
        max_caption_words = self.max_caption_length(captions)
            
        # Initialise a Keras Tokenizer
        tokenizer = Tokenizer()
            
        # Fit it on the captions so that it prepares a vocabulary of all words
        tokenizer.fit_on_texts(captions)
            
        # Get the size of the vocabulary
        vocab_size = len(tokenizer.word_index) + 1

        return (tokenizer, vocab_size, max_caption_words)

      #--------------------------------------------------
    def pad_text (self,text, max_length): 
        text = pad_sequences([text], maxlen=max_length, padding='post')[0]
            
        return (text)

    def data_prep(self,data_dict, tokenizer, max_length, vocab_size):
        X, y = list(), list()
        # For each image and list of captions
        for image_name, captions in data_dict.items():
            image_name = image_dir + image_name + '.jpg'
            # For each caption in the list of captions
            for caption in captions:
                # Convert the caption words into a list of word indices
                word_idxs = tokenizer.texts_to_sequences([caption])[0]

                # Pad the input text to the same fixed length
                pad_idxs = self.pad_text(word_idxs, max_length)
                        
                X.append(image_name)
                y.append(pad_idxs)
            
        return array(X), array(y)
        return X, y

    def map_func(self,img_name, cap):
        img_name_parts = img_name.split(b"Dataset")
        img_name = img_name_parts[0] + b"Dataset/" + img_name_parts[1]
        img_tensor = np.load(img_name.decode('utf-8') + '.npy')
        return img_tensor, cap

    def loss_function(self,real, pred):
        mask = tf.math.logical_not(tf.math.equal(real, 0))
        loss_ = loss_object(real, pred)

        mask = tf.cast(mask, dtype=loss_.dtype)
        loss_ *= mask

        return tf.reduce_mean(loss_)

    @tf.function
    def train_step(self,img_tensor, target):
        loss = 0
        # initializing the hidden state for each batch
        # because the captions are not related from image to image
        hidden = decoder.reset_state(batch_size=target.shape[0])

        dec_input = tf.expand_dims([tokenizer.word_index['startseq']] * target.shape[0], 1)

        with tf.GradientTape() as tape:
            features = encoder(img_tensor)
            for i in range(1, target.shape[1]):
                # passing the features through the decoder
                predictions, hidden, _ = decoder(dec_input, features, hidden)

                loss += self.loss_function(target[:, i], predictions)
                # using teacher forcing
                dec_input = tf.expand_dims(target[:, i], 1)

            total_loss = (loss / int(target.shape[1]))

            trainable_variables = encoder.trainable_variables + decoder.trainable_variables

            gradients = tape.gradient(loss, trainable_variables)

            optimizer.apply_gradients(zip(gradients, trainable_variables))

            return loss, total_loss

    def evaluate(self,image, max_length):
        attention_plot = np.zeros((max_length, attention_features_shape))

        hidden = decoder.reset_state(batch_size=1)

        temp_input = tf.expand_dims(self.load_image(image)[0], 0)
        img_tensor_val = self.image_features_extract_model(temp_input)
        img_tensor_val = tf.reshape(img_tensor_val, (img_tensor_val.shape[0],
                                                            -1,
                                                            img_tensor_val.shape[3]))

        features = encoder(img_tensor_val)

        dec_input = tf.expand_dims([tokenizer.word_index['startseq']], 0)
        result = []

        for i in range(max_length):
            predictions, hidden, attention_weights = decoder(dec_input,
                                                                  features,
                                                                  hidden)

            attention_plot[i] = tf.reshape(attention_weights, (-1, )).numpy()

            predicted_id = tf.random.categorical(predictions, 1)[0][0].numpy()
            result.append(tokenizer.index_word[predicted_id])

            if tokenizer.index_word[predicted_id] == 'endseq':
                return result, attention_plot

                dec_input = tf.expand_dims([predicted_id], 0)
                
        attention_plot = attention_plot[:len(result), :]
        return result, attention_plot


    def check_test(self,test_image_names, image_dict, image_dir, max_caption_words):
        # captions on the validation set
        rid = np.random.randint(0, len(test_image_names))
        image_name = test_image_names[rid]
        # real_caption = image_dict[image_name]
        if image_name in image_dict:
            real_caption = image_dict[image_name]
            image_path = image_dir +'/'+image_name + '.jpg'
            result, attention_plot = self.evaluate(image_path, max_caption_words)

            #from IPython.display import Image, display
            #display(Image(image_path))
            print('Real Caption:', real_caption)
            print('Prediction Caption:', ' '.join(result))
    # Rest of your code
        else:
            print(f"Key '{image_name}' not found in image_dict.")


        

    def play_audio(self,max_caption_words):
        from gtts import gTTS
        import os
        # Generate the caption
        result, attention_plot = self.evaluate(image_path, max_caption_words)
        caption = ' '.join(result)
        # Convert the caption to an audio file
        tts = gTTS(caption)
#-----------------------------------------------------------------
#-----------------------------------------------------------------
   

# Instantiate the ImageCaptioning
attention=ImageCaptioning()

print("Retrieving text files from zip folder")
doc = attention.load_captions("datasets/download_ds_file.zip","Flickr8k.token.txt")
image_dict = attention.captions_dict (doc)

print("Retrieving names of training images from text file")
training_imgname_doc = attention.load_captions("datasets/download_ds_file.zip","Flickr_8k.trainImages.txt")
training_image_names = attention.subset_image_name (training_imgname_doc)

print("Preprocessing captions:")
attention.captions_clean (image_dict)

print("Extracting images:")

# Path to the extracted folder
image_dir = "datasets/Flicker8k_Dataset"
# List all files in the extracted folder
file_names = os.listdir(image_dir)
# print(file_names)

print("Images Extracted")
training_image_paths = []
attention.process_image_dataset(image_dir, training_image_names)

training_dict = attention.subset_data_dict (image_dict, training_image_names)
# Prepare tokenizer
tokenizer, vocab_size, max_caption_words = attention.create_tokenizer(training_dict)

print("Data Preparation")
train_X, train_y = attention.data_prep(training_dict, tokenizer, max_caption_words, vocab_size)

# BATCH_SIZE = 64
BUFFER_SIZE = 1000
# Convert epoch number and batch size to integers
epoch_number = int(os.environ.get('EPOCH_NUMBER'))
batch_size = int(os.environ.get('BATCH_SIZE'))

print("\t Epoch number:", epoch_number)
print("\t Batch number:", batch_size)

dataset = tf.data.Dataset.from_tensor_slices((train_X, train_y))

# Use map to load the numpy files in parallel
dataset = dataset.map(lambda item1, item2: tf.numpy_function(attention.map_func, [item1, item2], [tf.float32, tf.int32]),num_parallel_calls=tf.data.experimental.AUTOTUNE)

# Shuffle and batch
dataset = dataset.shuffle(BUFFER_SIZE).batch(batch_size)
dataset = dataset.prefetch(buffer_size=tf.data.experimental.AUTOTUNE)

embedding_dim = 256
units = 512
vocab_size = vocab_size
num_steps = len(train_X) // batch_size
# Shape of the vector extracted from InceptionV3 is (64, 2048)
# These two variables represent that vector shape
features_shape = 2048
attention_features_shape = 64

encoder = CNN_Encoder(embedding_dim)
decoder = RNN_Decoder(embedding_dim, units, vocab_size)

optimizer = tf.keras.optimizers.Adam()
loss_object = tf.keras.losses.SparseCategoricalCrossentropy(
    from_logits=True, reduction='none')

loss_plot = []

start_epoch = 0

print("Training")
for epoch in range(start_epoch, epoch_number):
    start = time.time()
    total_loss = 0

    for (batch, (img_tensor, target)) in enumerate(dataset):
        batch_loss, t_loss = attention.train_step(img_tensor, target)
        total_loss += t_loss

        if batch % 100 == 0:
            average_batch_loss = batch_loss.numpy()/int(target.shape[1])
            print(f'Epoch {epoch+1} Batch {batch} Loss {average_batch_loss:.4f}')
        # storing the epoch end loss value to plot later
      
    loss_plot.append(total_loss / num_steps)

    print(f'Epoch {epoch+1} Loss {total_loss/num_steps:.6f}')
    print(f'Time taken for 1 epoch {time.time()-start:.2f} sec\n')


print("Evaluating the model with test set:")
print("\t Retrieving test text files from zip folder")
test_imgname_doc = attention.load_captions("datasets/download_ds_file.zip","Flickr_8k.trainImages.txt")
# test_image_dict = attention.captions_dict (test_imgname_doc)
print("\t Retrieving names of testing images from text file")
test_image_names = attention.subset_image_name(test_imgname_doc)
attention.check_test(list(test_image_names), image_dict, image_dir, max_caption_words)



