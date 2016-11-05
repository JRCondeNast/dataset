#!/usr/bin/env python
#
# Copyright 2016 The Open Images Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
#
# This script takes an Inception v3 checkpoint, runs the classifier
# on the image and prints top(n) predictions in the human-readable form.
# Example:
#   $ wget -O /tmp/cat.jpg https://farm6.staticflickr.com/5470/9372235876_d7d69f1790_b.jpg
#   $ ./tools/classify.py /tmp/cat.jpg
#   5723: /m/0jbk - animal (score = 0.94)
#   3473: /m/04rky - mammal (score = 0.93)
#   4605: /m/09686 - vertebrate (score = 0.91)
#   1261: /m/01yrx - cat (score = 0.90)
#   3981: /m/068hy - pet (score = 0.87)
#   841: /m/01l7qd - whiskers (score = 0.83)
#   2430: /m/0307l - cat-like mammal (score = 0.78)
#   4349: /m/07k6w8 - small to medium-sized cats (score = 0.75)
#   2537: /m/035qhg - fauna (score = 0.47)
#   1776: /m/02cqfm - close-up (score = 0.45)
#
# Make sure to download the ANN weights and support data with:
# $ ./tools/download_data.sh

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import math
import sys
import os.path

import numpy as np
import tensorflow as tf

from tensorflow.contrib.slim.python.slim.nets import inception
from tensorflow.python.framework import ops
from tensorflow.python.ops import control_flow_ops
from tensorflow.python.ops import data_flow_ops
from tensorflow.python.ops import variables
from tensorflow.python.training import saver as tf_saver
from tensorflow.python.training import supervisor

slim = tf.contrib.slim
FLAGS = None

def PreprocessImage(image_path):
  """Load and preprocess an image.

  Args:
    image_path: path to an image
  Returns:
    An ops.Tensor that produces the preprocessed image.
  """
  if not os.path.exists(image_path):
    tf.logging.fatal('Input image does not exist %s', image_path)
  img_data = tf.gfile.FastGFile(image_path).read()

  # Decode Jpeg data and convert to float.
  img = tf.cast(tf.image.decode_jpeg(img_data, channels=3), tf.float32)

  # Make into a 4D tensor by setting a 'batch size' of 1.
  img = tf.expand_dims(img, [0])

  img = tf.image.crop_and_resize(
      img,
      # Whole image
      tf.constant([0, 0, 1.0, 1.0], shape=[1, 4]),
      # One box
      tf.constant([0], shape=[1]),
      # Target size is image_size x image_size
      tf.constant([FLAGS.image_size, FLAGS.image_size], shape=[2]))

  # Center the image about 128.0 (which is done during training) and normalize.
  img = tf.mul(img, 1.0/127.5)
  return tf.sub(img, 1.0)

def LoadLabelMaps(num_classes, labelmap_path, dict_path):
  """Load index->mid and mid->display name maps.

  Args:
    labelmap_path: path to the file with the list of mids, describing predictions.
    dict_path: path to the dict.csv that translates from mids to display names.
  Returns:
    labelmap: an index to mid list
    label_dict: mid to display name dictionary
  """
  labelmap = [line.rstrip() for line in tf.gfile.GFile(labelmap_path).readlines()]
  if len(labelmap) != num_classes:
    tf.logging.fatal(
        "Label map loaded from {} contains {} lines while the number of classes is {}".format(
            labelmap_path, len(labelmap), num_classes))
    sys.exit(1)

  label_dict = {}
  for line in tf.gfile.GFile(dict_path).readlines():
    words = [word.strip(' "\n') for word in line.split(',', 1)]
    label_dict[words[0]] = words[1]

  return labelmap, label_dict

def main(args):
  if not os.path.exists(FLAGS.checkpoint):
    tf.logging.fatal(
        'Checkpoint %s does not exist. Have you download it? See tools/download_data.sh',
        FLAGS.checkpoint)
  g = tf.Graph()
  with g.as_default():
    input_image = PreprocessImage(FLAGS.image_path[0])

    with slim.arg_scope(inception.inception_v3_arg_scope()):
      logits, end_points = inception.inception_v3(
          input_image, num_classes=FLAGS.num_classes, is_training=False)

    predictions = end_points['multi_predictions'] = tf.nn.sigmoid(
        logits, name='multi_predictions')
    init_op = control_flow_ops.group(variables.initialize_all_variables(),
                                     variables.initialize_local_variables(),
                                     data_flow_ops.initialize_all_tables())
    saver = tf_saver.Saver()
    sess = tf.Session()
    saver.restore(sess, FLAGS.checkpoint)

    # Run the evaluation on the image
    predictions_eval = np.squeeze(sess.run(predictions))

  # Print top(n) results
  labelmap, label_dict = LoadLabelMaps(FLAGS.num_classes, FLAGS.labelmap, FLAGS.dict)

  top_k = predictions_eval.argsort()[-FLAGS.n:][::-1]
  for idx in top_k:
    mid = labelmap[idx]
    display_name = label_dict.get(mid, 'unknown')
    score = predictions_eval[idx]
    print('{}: {} - {} (score = {:.2f})'.format(idx, mid, display_name, score))

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--checkpoint', type=str, default='data/2016_08/model.ckpt',
                      help='Checkpoint to run inference on.')
  parser.add_argument('--labelmap', type=str, default='data/2016_08/labelmap.txt',
                      help='Label map that translates from index to mid.')
  parser.add_argument('--dict', type=str, default='dict.csv',
                      help='Path to a dict.csv that translates from mid to a display name.')
  parser.add_argument('--image_size', type=int, default=299,
                      help='Image size to run inference on.')
  parser.add_argument('--num_classes', type=int, default=6012,
                      help='Number of output classes.')
  parser.add_argument('--n', type=int, default=10,
                      help='Number of top predictions to print.')
  parser.add_argument('image_path', nargs=1, default='')
  FLAGS = parser.parse_args()
  tf.app.run()