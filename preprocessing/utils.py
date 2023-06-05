import os

import numpy as np
import pandas as pd
import tensorflow as tf
import yaml
from sklearn.preprocessing import StandardScaler

from preprocessing.opp_preprocess import *
from preprocessing.pamap2_preprocess import *
from preprocessing.daphnet_preprocess import get_daphnet_data
from preprocessing.sliding_window import create_windowed_dataset


def get_activity_dict(activity_map: dict, novel_classes: list):
    _activity_map = activity_map.copy()
    novel_map = dict()

    for activity_class in novel_classes:
        novel_map[str(activity_class)] = activity_map[str(activity_class)]
        _activity_map.pop(str(activity_class))

    return _activity_map, novel_map


def get_train_test_data(dataset, holdout=False):

    metadata_file = open('configs/metadata.yaml', mode='r')

    if dataset == 'opp':
        metadata = yaml.load(metadata_file, Loader=yaml.FullLoader)[
            'opp_preprocess']
        FEATURES = [str(i) for i in range(77)]
        LOCO_LABEL_COL = 77
        MID_LABEL_COL = 78
        HI_LABEL_COL = 79
        SUBJECT_ID = 80
        RUN_ID = 81
        if not os.path.exists(os.path.join('data', 'processed', 'clean_opp.csv')):
            prepare_opp_data()
        df = pd.read_csv(os.path.join('data', 'processed', 'clean_opp.csv'))

        df = df[df[str(HI_LABEL_COL)] != 0]
        df[FEATURES] = df[FEATURES].interpolate(method='linear', axis=0)
        df = df.fillna(0)

        scaler = StandardScaler()
        df[FEATURES] = scaler.fit_transform(df[FEATURES])

        if holdout:
            NOVEL_CLASSES = metadata['NOVEL_CLASSES']
            holdout_data = df.loc[df[str(HI_LABEL_COL)].isin(NOVEL_CLASSES)]
            novel_data = holdout_data.copy().reset_index(drop=True)
            df = df.drop(holdout_data.copy().index)
            df = df.reset_index(drop=True)

        BENCHMARK_TEST = ((df[str(SUBJECT_ID)] == 2) | (df[str(SUBJECT_ID)] == 3)) & (
            (df[str(RUN_ID)] == 4) | (df[str(RUN_ID)] == 5))

        train_df = df[~ BENCHMARK_TEST]
        test_df = df[BENCHMARK_TEST]

        SLIDING_WINDOW_LENGTH = metadata['sliding_win_len']
        SLIDING_WINDOW_STEP = metadata['sliding_win_stride']
        N_WINDOW, N_TIMESTEP = metadata['n_window'], metadata['n_timestep']

        X_train, y_train, m_labels_tr, loco_labels_tr = create_windowed_dataset_opp(train_df, FEATURES, str(
            HI_LABEL_COL), MID_LABEL_COL, LOCO_LABEL_COL, window_size=SLIDING_WINDOW_LENGTH, stride=SLIDING_WINDOW_STEP)
        X_test, y_test, m_labels_ts, loco_labels_ts = create_windowed_dataset_opp(test_df, FEATURES, str(
            HI_LABEL_COL), MID_LABEL_COL, LOCO_LABEL_COL, window_size=SLIDING_WINDOW_LENGTH, stride=SLIDING_WINDOW_STEP)
        if holdout:
            X_holdout, y_holdout, m_labels_holdout, loco_labels_holdout = create_windowed_dataset_opp(novel_data, FEATURES, str(
                HI_LABEL_COL), MID_LABEL_COL, LOCO_LABEL_COL, window_size=SLIDING_WINDOW_LENGTH, stride=SLIDING_WINDOW_STEP)
            X_holdout = X_holdout.reshape(
                (X_holdout.shape[0], N_WINDOW, N_TIMESTEP, len(FEATURES)))
            y_holdout = tf.keras.utils.to_categorical(y_holdout)

        X_train = X_train.reshape(
            (X_train.shape[0], N_WINDOW, N_TIMESTEP, len(FEATURES)))
        X_test = X_test.reshape(
            (X_test.shape[0], N_WINDOW, N_TIMESTEP, len(FEATURES)))

        y_train = tf.keras.utils.to_categorical(y_train)
        y_test = tf.keras.utils.to_categorical(y_test)

        if holdout:
            return (X_train, y_train),  (X_test, y_test), (X_holdout, y_holdout)
        else:
            return (X_train, y_train),  (X_test, y_test)

    elif dataset == 'pamap2':
        metadata = yaml.load(metadata_file, Loader=yaml.FullLoader)[
            'pamap2_preprocess']
        file_path = os.path.join('data', 'processed', 'pamap2_106.h5')
        if not os.path.exists(file_path):
            train_test_files = metadata['file_list']
            use_columns = metadata['columns_list']
            output_file_name = file_path
            label_to_id = metadata['label_to_id']
            read_dataset_pamap2(train_test_files, use_columns,
                                output_file_name, label_to_id)

        (train_x, train_y), (val_x, val_y), (test_x,
                                             test_y) = preprocess_pamap2(file_path, print_debug=True, downsample=False)

        SLIDING_WINDOW_LENGTH = metadata['sliding_win_len']
        SLIDING_WINDOW_STEP = metadata['sliding_win_stride']
        N_WINDOW, N_TIMESTEP = metadata['n_window'], metadata['n_timestep']

        if holdout:
            NOVEL_CLASSES = metadata['NOVEL_CLASSES']
            X_holdout_ts = test_x[np.isin(test_y, NOVEL_CLASSES)]
            y_holdout_ts = test_y[np.isin(test_y, NOVEL_CLASSES)]
            X_holdout_tr = train_x[np.isin(train_y, NOVEL_CLASSES)]
            y_holdout_tr = train_y[np.isin(train_y, NOVEL_CLASSES)]

            holdout_X = np.concatenate([X_holdout_ts, X_holdout_tr], axis=0)
            holdout_y = np.concatenate([y_holdout_ts, y_holdout_tr], axis=0)

            test_x = test_x[~ np.isin(test_y, NOVEL_CLASSES)]
            test_y = test_y[~ np.isin(test_y, NOVEL_CLASSES)]
            train_x = train_x[~ np.isin(train_y, NOVEL_CLASSES)]
            train_y = train_y[~ np.isin(train_y, NOVEL_CLASSES)]

        X_train, y_train = create_windowed_dataset(
            None, None, None, X=train_x, y=train_y, window_size=SLIDING_WINDOW_LENGTH, stride=SLIDING_WINDOW_STEP)
        X_test, y_test = create_windowed_dataset(
            None, None, None, X=test_x, y=test_y, window_size=SLIDING_WINDOW_LENGTH, stride=SLIDING_WINDOW_STEP)

        X_train = X_train.reshape((X_train.shape[0], N_WINDOW, N_TIMESTEP, 18))
        X_test = X_test.reshape((X_test.shape[0], N_WINDOW, N_TIMESTEP, 18))
        y_train = tf.keras.utils.to_categorical(y_train, num_classes=19)
        y_test = tf.keras.utils.to_categorical(y_test, num_classes=19)
        y_train_mid = np.repeat(np.expand_dims(y_train, axis=1), repeats=N_WINDOW, axis=1)
        y_test_mid = np.repeat(np.expand_dims(y_test, axis=1), repeats=N_WINDOW, axis=1)

        if holdout:
            X_holdout, y_holdout = create_windowed_dataset(None, None, None, X=holdout_X, y=holdout_y, window_size=SLIDING_WINDOW_LENGTH, stride = SLIDING_WINDOW_STEP)
            X_holdout = X_holdout.reshape((X_holdout.shape[0], N_WINDOW, N_TIMESTEP, 18))
            y_holdout = tf.keras.utils.to_categorical(y_holdout, num_classes=19)
            return (X_train, y_train, y_train_mid),  (X_test, y_test, y_test_mid), (X_holdout, y_holdout)

        return (X_train, y_train, y_train_mid), (None, None, None),  (X_test, y_test, y_test_mid)

    elif dataset == 'daphnet':
        metadata = yaml.load(metadata_file, Loader=yaml.FullLoader)['daphnet_preprocess']
        FEATURES = metadata['feature_list']
        LABELS = metadata['label_column']
        SLIDING_WINDOW_LENGTH = metadata['sliding_win_len']
        SLIDING_WINDOW_STEP = metadata['sliding_win_stride']
        N_WINDOW, N_TIMESTEP = metadata['n_window'], metadata['n_timestep']

        if os.path.exists(os.path.join(metadata['data_dir'])):
            df = pd.read_csv(os.path.join(metadata['data_dir']))
        else:
            df = get_daphnet_data()

        df = df.fillna(0)
        # if not holdout:
        #     df = df[df[LABELS] != 0]
        #     df[LABELS] = df[LABELS]
        scaler = StandardScaler()
        df[FEATURES] = scaler.fit_transform(df[FEATURES])

        if holdout:
            NOVEL_CLASSES = [0]
            holdout_data = df.loc[df['Label'].isin(NOVEL_CLASSES)]
            novel_data = holdout_data.copy().reset_index(drop=True)

            df = df.drop(holdout_data.copy().index)
            df = df.reset_index(drop=True)

            X_holdout, y_holdout = create_windowed_dataset(novel_data, FEATURES, LABELS, window_size=SLIDING_WINDOW_LENGTH, stride=SLIDING_WINDOW_STEP)
            X_holdout = X_holdout.reshape((X_holdout.shape[0], N_WINDOW, N_TIMESTEP, len(FEATURES)))
            y_holdout = tf.keras.utils.to_categorical(y_holdout)
        
        train_df = df[(df['Subject'] != metadata['benchmark_val_sub']) & (df['Subject'] != metadata['benchmark_test_sub'])]
        test_df = df[df['Subject'] == metadata['benchmark_val_sub']]
        val_df = df[df['Subject'] == metadata['benchmark_test_sub']]

        X_train, y_train = create_windowed_dataset(train_df, FEATURES, 'Label', window_size=SLIDING_WINDOW_LENGTH, stride=SLIDING_WINDOW_STEP)
        X_val, y_val = create_windowed_dataset(
            val_df, FEATURES, 'Label', window_size=SLIDING_WINDOW_LENGTH, stride=SLIDING_WINDOW_STEP)
        X_test, y_test = create_windowed_dataset(
            test_df, FEATURES, 'Label', window_size=SLIDING_WINDOW_LENGTH, stride=SLIDING_WINDOW_STEP)

        X_train = X_train.reshape(
            (X_train.shape[0], N_WINDOW, N_TIMESTEP, len(FEATURES)))
        X_val = X_val.reshape(
            (X_val.shape[0], N_WINDOW, N_TIMESTEP, len(FEATURES)))
        X_test = X_test.reshape(
            (X_test.shape[0], N_WINDOW, N_TIMESTEP, len(FEATURES)))

        y_train = tf.keras.utils.to_categorical(y_train, num_classes=3)
        y_val = tf.keras.utils.to_categorical(y_val, num_classes=3)
        y_test = tf.keras.utils.to_categorical(y_test, num_classes=3)

        y_train_mid = np.repeat(np.expand_dims(y_train, axis=1), repeats=metadata['n_window'], axis=1)
        y_val_mid = np.repeat(np.expand_dims(y_val, axis=1), repeats=metadata['n_window'], axis=1)
        y_test_mid = np.repeat(np.expand_dims(y_test, axis=1), repeats=metadata['n_window'], axis=1)

        if holdout:
            return (X_train, y_train),  (X_test, y_test), (X_holdout, y_holdout)
        else:
            return (X_train, y_train, y_train_mid), (X_val, y_val, y_val_mid), (X_test, y_test, y_test_mid)