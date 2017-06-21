import numpy as np
from keras.models import Sequential
from keras.layers import Dense
from keras.layers import Dropout
from keras.layers import LSTM
from keras.layers import TimeDistributed

from keras.callbacks import ModelCheckpoint
from keras.utils import np_utils

import click
import os
import codecs
import glob2
import glob
import json
import re


def initialize_model(n, dropout, seq_length, chars, output_size, layers,
                     loss='categorical_crossentropy', optimizer='adam'):
    model = Sequential()
    model.add(LSTM(n, input_shape=(seq_length, len(chars)), return_sequences=True))
    model.add(Dropout(dropout))

    for _ in range(layers-1):
        model.add(LSTM(n, return_sequences=True))
        model.add(Dropout(dropout))

        model.add(TimeDistributed(Dense(len(chars), activation='softmax')))

        model.compile(loss='categorical_crossentropy', optimizer='adam', metrics=['accuracy'])

    return model


def load_weights(model, weights_dir, loss='categorical_crossentropy',
                 optimizer='adam'):
    epoch = 0
    weight_files = glob2.glob('{}{}*.hdf5'.format(weights_dir, os.sep))
    if weight_files != []:
        fname = sorted(weight_files)[-1]
        print('Loading weights from {}'.format(fname))

        model.load_weights(fname)
        model.compile(loss=loss, optimizer=optimizer)

        m = re.match(r'.+-(\d\d).hdf5', fname)
        if m:
            epoch = int(m.group(1))

    return epoch, model


def create_data(ocr_text, gs_text, char_to_int, n_vocab, seq_length=25, batch_size=100):
    """Create padded one-hot encoded data sets from text.

    A sample consists of seq_length characters from texts from ocr_texts
    (includes empty characters) (input), and seq_length characters from
    gs_texts (includes empty characters) (output).
    ocr_texts and gs_tetxts contain aligned arrays of characters.
    Because of the empty characters ('' in the character arrays), the input
    and output sequences may not have equal length. Therefore input and
    output are padded with a padding character (newline).
    """
    dataX = []
    dataY = []
    text_length = len(ocr_text)
    for i in range(0, text_length-seq_length +1, 1):
        seq_in = ocr_text[i:i+seq_length]
        seq_out = gs_text[i:i+seq_length]
        dataX.append(''.join(seq_in))
        dataY.append(''.join(seq_out))
    return len(dataX), data_generator(dataX, dataY, seq_length, n_vocab, char_to_int, batch_size)


def data_generator(dataX, dataY, seq_length, n_vocab, char_to_int, batch_size):
    while 1:
        for batch_idx in range(0, len(dataX), batch_size):
            print batch_idx
            X = np.zeros((batch_size, seq_length, n_vocab), dtype=np.bool)
            Y = np.zeros((batch_size, seq_length, n_vocab), dtype=np.bool)
            for i, (sentenceX, sentenceY) in enumerate(zip(dataX[batch_idx:batch_idx+batch_size], dataY[batch_idx:batch_idx+batch_size])):
                for j, c in enumerate(sentenceX):
                    X[i, j, char_to_int[c]] = 1
                for j in range(seq_length-len(sentenceX)):
                    X[i, len(sentenceX) + j, char_to_int[u'\n']] = 1
                for j, c in enumerate(sentenceY):
                    Y[i, j, char_to_int[c]] = 1
                for j in range(seq_length-len(sentenceY)):
                    Y[i, len(sentenceY) + j, char_to_int[u'\n']] = 1
            yield X, Y


def read_texts(data_files, data_dir):
    raw_text = []
    gs = []
    ocr = []

    for df in data_files:
        with codecs.open(os.path.join(data_dir, df), encoding='utf-8') as f:
            aligned = json.load(f)

        ocr.append(aligned['ocr'])
        gs.append(aligned['gs'])

        raw_text.append(''.join(aligned['ocr']))
        raw_text.append(''.join(aligned['gs']))

    # Make a single array, containing the character-aligned text of all data
    # files
    gs_text = []
    map(gs_text.extend, gs)

    ocr_text = []
    map(ocr_text.extend, ocr)

    return ' '.join(raw_text), gs_text, ocr_text


@click.command()
@click.argument('datasets', type=click.File())
@click.argument('data_dir', type=click.Path(exists=True))
@click.option('--weights_dir', '-w', default=os.getcwd(), type=click.Path())
def train_lstm(datasets, data_dir, weights_dir):
    # lees data in en maak character mappings
    # genereer trainings data
    seq_length = 25
    num_nodes = 256
    layers = 3
    batch_size = 100

    division = json.load(datasets)

    raw_val, gs_val, ocr_val = read_texts(division.get('val'), data_dir)
    raw_test, gs_test, ocr_test = read_texts(division.get('test'), data_dir)
    raw_train, gs_train, ocr_train = read_texts(division.get('train'), data_dir)

    raw_text = ''.join([raw_val, raw_test, raw_train])

    #print('Number of texts: {}'.format(len(data_files)))

    chars = sorted(list(set(raw_text)))
    chars.append(u'\n')                      # padding character
    char_to_int = dict((c, i) for i, c in enumerate(chars))

    n_chars = len(raw_text)
    n_vocab = len(chars)

    print('Total Characters: {}'.format(n_chars))
    print('Total Vocab: {}'.format(n_vocab))

    numTrainSamples, trainDataGen = create_data(ocr_train, gs_train, char_to_int, n_vocab, seq_length=seq_length, batch_size=batch_size
    numTestSamples, testDataGen = create_data(ocr_test, gs_test, char_to_int, n_vocab, seq_length=seq_length, batch_size=batch_size)
    numValSamples, valDataGen = create_data(ocr_val, gs_val, char_to_int, n_vocab, seq_length=seq_length, batch_size=batch_size)

    n_patterns = numTrainSamples
    print("Train Patterns: {}".format(n_patterns))
    print("Validation Patterns: {}".format(numValSamples))
    print("Test Patterns: {}".format(numTestSamples))
    print('Total: {}'.format(numTrainSamples+numTestSamples+numValSamples))

    model = initialize_model(num_nodes, 0.5, seq_length, chars, n_vocab, layers)
    epoch, model = load_weights(model, weights_dir)

    # initialize saving of weights
    filepath = os.path.join(weights_dir, '{loss:.4f}-{epoch:02d}.hdf5')
    checkpoint = ModelCheckpoint(filepath, monitor='loss', verbose=1,
                                 save_best_only=True, mode='min')
    callbacks_list = [checkpoint]

    # do training (and save weights)
    model.fit_generator(trainDataGen, steps_per_epoch=numTrainSamples/batch_size, epochs=15, validation_data=valDataGen, validation_steps=numValSamples/batch_size, callbacks=callbacks_list, initial_epoch=epoch)


if __name__ == '__main__':
    train_lstm()
