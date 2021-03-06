import pandas as pd
import numpy as np
from tqdm import tqdm
from sklearn.metrics import roc_auc_score
from lightgbm.sklearn import LGBMClassifier
from collections import defaultdict
import gc
import time

pd.set_option('display.max_columns', None)

def reduce_mem(df, cols):
    start_mem = df.memory_usage().sum() / 1024 ** 2
    for col in tqdm(cols):
        col_type = df[col].dtypes
        if col_type != object:
            c_min = df[col].min()
            c_max = df[col].max()
            if str(col_type)[:3] == 'int':
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
                elif c_min > np.iinfo(np.int64).min and c_max < np.iinfo(np.int64).max:
                    df[col] = df[col].astype(np.int64)
            else:
                if c_min > np.finfo(np.float16).min and c_max < np.finfo(np.float16).max:
                    df[col] = df[col].astype(np.float16)
                elif c_min > np.finfo(np.float32).min and c_max < np.finfo(np.float32).max:
                    df[col] = df[col].astype(np.float32)
                else:
                    df[col] = df[col].astype(np.float64)
    end_mem = df.memory_usage().sum() / 1024 ** 2
    print('{:.2f} Mb, {:.2f} Mb ({:.2f} %)'.format(start_mem, end_mem, 100 * (start_mem - end_mem) / start_mem))
    gc.collect()
    return df

## 从官方baseline里面抽出来的评测函数

def uAUC(labels, preds, user_id_list):
    """Calculate user AUC"""
    user_pred = defaultdict(lambda: [])
    user_truth = defaultdict(lambda: [])
    for idx, truth in enumerate(labels):
        user_id = user_id_list[idx]
        pred = preds[idx]
        truth = labels[idx]
        user_pred[user_id].append(pred)
        user_truth[user_id].append(truth)

    user_flag = defaultdict(lambda: False)
    for user_id in set(user_id_list):
        truths = user_truth[user_id]
        flag = False
        # 若全是正样本或全是负样本，则flag为False
        for i in range(len(truths) - 1):
            if truths[i] != truths[i + 1]:
                flag = True
                break
        user_flag[user_id] = flag

    total_auc = 0.0
    size = 0.0
    for user_id in user_flag:
        if user_flag[user_id]:
            auc = roc_auc_score(np.asarray(user_truth[user_id]), np.asarray(user_pred[user_id]))
            total_auc += auc
            size += 1.0
    user_auc = float(total_auc)/size
    return user_auc

y_list = ['read_comment', 'like', 'click_avatar', 'forward', 'favorite', 'comment', 'follow']
max_day = 15

## 读取训练集
train = pd.read_csv('data/wechat_algo_data1/user_action.csv')
print(train.shape)
for y in y_list:
    print(y, train[y].mean())

## 读取测试集
test = pd.read_csv('data/wechat_algo_data1/test_a.csv')
test['date_'] = max_day
print(test.shape)

## 合并处理
df = pd.concat([train, test], axis=0, ignore_index=True)
print(df.head(3))

## 读取视频信息表
feed_info = pd.read_csv('data/wechat_algo_data1/feed_info.csv')

## 读取feed embedding
from sklearn.decomposition import PCA
def feed_embedding_pca():
    feed_embedding = pd.read_csv('data/wechat_algo_data1/feed_embeddings.csv')
    feed = np.array(feed_embedding.feed_embedding.str.split().tolist())
    print(feed.shape)
    pca = PCA(n_components=64)
    res = pca.fit_transform(feed)
    print(res.shape)
    df = pd.DataFrame(res)
    df['feedid'] = feed_embedding['feedid']
    return df
feed_embedding = feed_embedding_pca()
feed_embedding = feed_embedding.set_index('feedid')

## 此份baseline只保留这三列
feed_info = feed_info[[
    'feedid', 'authorid', 'videoplayseconds', 'bgm_song_id', 'bgm_singer_id', 'machine_tag_list', 'manual_tag_list', 'machine_keyword_list', 'manual_keyword_list'
]]

df = df.merge(feed_info, on='feedid', how='left')
df = df.merge(feed_embedding, on='feedid', how='left')
## 视频时长是秒，转换成毫秒，才能与play、stay做运算
df['videoplayseconds'] *= 1000
## 是否观看完视频
df['is_finish'] = (df['play'] >= df['videoplayseconds']).astype('int8')
df['play_times'] = df['play'] / df['videoplayseconds']

play_cols = ['is_finish', 'play_times', 'play', 'stay']

# tag
df['machine_tag_list'] = df['machine_tag_list'].apply(lambda x: str(x).split(";") if str(x)!='nan' else [])
df['machine_tag_1'] = df['machine_tag_list'].apply(lambda x: int(x[0].split(" ")[0]) if len(x)>0 else np.nan)
df['machine_tag_2'] = df['machine_tag_list'].apply(lambda x: int(x[1].split(" ")[0]) if len(x)>1 else np.nan)
df['machine_tag_3'] = df['machine_tag_list'].apply(lambda x: int(x[2].split(" ")[0]) if len(x)>2 else np.nan)
df['machine_tag_4'] = df['machine_tag_list'].apply(lambda x: int(x[3].split(" ")[0]) if len(x)>3 else np.nan)

df['manual_tag_list'] = df['manual_tag_list'].apply(lambda x: str(x).split(";") if str(x)!='nan' else [])
df['manual_tag_1'] = df['manual_tag_list'].apply(lambda x: int(x[0]) if len(x)>0 else np.nan)
df['manual_tag_2'] = df['manual_tag_list'].apply(lambda x: int(x[1]) if len(x)>1 else np.nan)
df['manual_tag_3'] = df['manual_tag_list'].apply(lambda x: int(x[2]) if len(x)>2 else np.nan)
df['manual_tag_4'] = df['manual_tag_list'].apply(lambda x: int(x[3]) if len(x)>3 else np.nan)

# keyword
df['machine_keyword_list'] = df['machine_keyword_list'].apply(lambda x: str(x).split(";") if str(x)!='nan' else [])
df['machine_keyword_1'] = df['machine_keyword_list'].apply(lambda x: int(x[0]) if len(x)>0 else np.nan)
df['machine_keyword_2'] = df['machine_keyword_list'].apply(lambda x: int(x[1]) if len(x)>1 else np.nan)
df['machine_keyword_3'] = df['machine_keyword_list'].apply(lambda x: int(x[2]) if len(x)>2 else np.nan)
df['machine_keyword_4'] = df['machine_keyword_list'].apply(lambda x: int(x[3]) if len(x)>3 else np.nan)

df['manual_keyword_list'] = df['manual_keyword_list'].apply(lambda x: str(x).split(";") if str(x)!='nan' else [])
df['manual_keyword_1'] = df['manual_keyword_list'].apply(lambda x: int(x[0]) if len(x)>0 else np.nan)
df['manual_keyword_2'] = df['manual_keyword_list'].apply(lambda x: int(x[1]) if len(x)>1 else np.nan)
df['manual_keyword_3'] = df['manual_keyword_list'].apply(lambda x: int(x[2]) if len(x)>2 else np.nan)
df['manual_keyword_4'] = df['manual_keyword_list'].apply(lambda x: int(x[3]) if len(x)>3 else np.nan)



## 统计历史5天的曝光、转化、视频观看等情况
n_day = 7
for stat_cols in tqdm([['userid'], ['feedid'], ['authorid'], ['bgm_song_id'], ['bgm_singer_id'], ['manual_keyword_1'], ['machine_keyword_1'],['manual_tag_1'], ['machine_tag_1'],['userid', 'authorid'], ['userid', 'bgm_song_id'], ['userid', 'bgm_singer_id'], ['userid','manual_keyword_1'], ['userid', 'machine_keyword_1'], ['userid', 'manual_tag_1'], ['userid', 'machine_tag_1']]):
    f = '_'.join(stat_cols)
    stat_df = pd.DataFrame()
    for target_day in range(2, max_day + 1):
        left, right = max(target_day - n_day, 1), target_day - 1
        tmp = df[((df['date_'] >= left) & (df['date_'] <= right))].reset_index(drop=True)
        tmp['date_'] = target_day
        tmp['{}_{}day_count'.format(f, n_day)] = tmp.groupby(stat_cols)['date_'].transform('count')
        g = tmp.groupby(stat_cols)
        tmp['{}_{}day_finish_rate'.format(f, n_day)] = g[play_cols[0]].transform('mean')
        feats = ['{}_{}day_count'.format(f, n_day), '{}_{}day_finish_rate'.format(f, n_day)]

        for x in play_cols[1:]:
            for stat in ['max', 'mean']:
                tmp['{}_{}day_{}_{}'.format(f, n_day, x, stat)] = g[x].transform(stat)
                feats.append('{}_{}day_{}_{}'.format(f, n_day, x, stat))

        for y in y_list:
            tmp['{}_{}day_{}_sum'.format(f, n_day, y)] = g[y].transform('sum')
            tmp['{}_{}day_{}_mean'.format(f, n_day, y)] = g[y].transform('mean')
            feats.extend(['{}_{}day_{}_sum'.format(f, n_day, y), '{}_{}day_{}_mean'.format(f, n_day, y)])

        tmp = tmp[stat_cols + feats + ['date_']].drop_duplicates(stat_cols + ['date_']).reset_index(drop=True)
        stat_df = pd.concat([stat_df, tmp], axis=0, ignore_index=True)
        del g, tmp

    df = df.merge(stat_df, on=stat_cols + ['date_'], how='left')
    del stat_df
    gc.collect()

## 全局信息统计，包括曝光、偏好等
for f in tqdm(['userid', 'feedid', 'authorid', 'bgm_song_id', 'bgm_singer_id', 'manual_keyword_1', 'machine_keyword_1', 'manual_tag_1', 'machine_tag_1']):
    df[f + '_count'] = df[f].map(df[f].value_counts())
for f1, f2 in tqdm([['userid', 'feedid'], ['userid', 'authorid'], ['userid', 'bgm_song_id'], ['userid', 'bgm_singer_id'], ['userid', 'manual_keyword_1'],['userid', 'machine_keyword_1'],['userid', 'manual_tag_1'], ['userid', 'machine_tag_1']]):
    df['{}_in_{}_nunique'.format(f1, f2)] = df.groupby(f2)[f1].transform('nunique')
    df['{}_in_{}_nunique'.format(f2, f1)] = df.groupby(f1)[f2].transform('nunique')
for f1, f2 in tqdm([['userid', 'authorid'], ['userid', 'bgm_song_id'], ['userid', 'bgm_singer_id'], ['userid', 'manual_keyword_1'], ['userid', 'machine_keyword_1'],['userid', 'manual_tag_1'], ['userid', 'machine_tag_1']]):
    df['{}_{}_count'.format(f1, f2)] = df.groupby([f1, f2])['date_'].transform('count')
    df['{}_in_{}_count_prop'.format(f1, f2)] = df['{}_{}_count'.format(f1, f2)] / (df[f2 + '_count'] + 1)
    df['{}_in_{}_count_prop'.format(f2, f1)] = df['{}_{}_count'.format(f1, f2)] / (df[f1 + '_count'] + 1)
df['videoplayseconds_in_userid_mean'] = df.groupby('userid')['videoplayseconds'].transform('mean')
df['videoplayseconds_in_authorid_mean'] = df.groupby('authorid')['videoplayseconds'].transform('mean')
df['feedid_in_authorid_nunique'] = df.groupby('authorid')['feedid'].transform('nunique')

## 标准的降内存方法
df = reduce_mem(df, [f for f in df.columns if f not in ['date_', 'machine_tag_list', 'manual_tag_list', 'machine_keyword_list', 'manual_keyword_list'] + play_cols + y_list])

train = df[~df['read_comment'].isna()].reset_index(drop=True)
test = df[df['read_comment'].isna()].reset_index(drop=True)


cols = [f for f in df.columns if f not in ['date_', 'machine_tag_list', 'manual_tag_list', 'machine_keyword_list', 'manual_keyword_list'] + play_cols + y_list]
print(train[cols].shape)

trn_x = train[train['date_'] < 14].reset_index(drop=True)
val_x = train[train['date_'] == 14].reset_index(drop=True)

##################### 线下验证 #####################
uauc_list = []
r_list = []
for y in y_list[:4]:
    print('=========', y, '=========')
    t = time.time()
    clf = LGBMClassifier(
        learning_rate=0.05,
        n_estimators=5000,
        num_leaves=63,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=2021,
        metric='None'
    )

    clf.fit(
        trn_x[cols], trn_x[y],
        eval_set=[(val_x[cols], val_x[y])],
        eval_metric='auc',
        early_stopping_rounds=100,
        verbose=50
    )

    val_x[y + '_score'] = clf.predict_proba(val_x[cols])[:, 1]
    val_uauc = uAUC(val_x[y], val_x[y + '_score'], val_x['userid'])
    uauc_list.append(val_uauc)
    print(val_uauc)
    r_list.append(clf.best_iteration_)
    print('runtime: {}\n'.format(time.time() - t))

weighted_uauc = 0.4 * uauc_list[0] + 0.3 * uauc_list[1] + 0.2 * uauc_list[2] + 0.1 * uauc_list[3]
print(uauc_list)
print(weighted_uauc)

##################### 全量训练 #####################
r_dict = dict(zip(y_list[:4], r_list))
for y in y_list[:4]:
    print('=========', y, '=========')
    t = time.time()
    clf = LGBMClassifier(
        learning_rate=0.02,
        n_estimators=r_dict[y],
        num_leaves=63,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=2021
    )

    clf.fit(
        train[cols], train[y],
        eval_set=[(train[cols], train[y])],
        early_stopping_rounds=r_dict[y],
        verbose=100
    )

    test[y] = clf.predict_proba(test[cols])[:, 1]
    print('runtime: {}\n'.format(time.time() - t))
test[['userid', 'feedid'] + y_list[:4]].to_csv(
    'sub_%.6f_%.6f_%.6f_%.6f_%.6f.csv' % (weighted_uauc, uauc_list[0], uauc_list[1], uauc_list[2], uauc_list[3]),
    index=False
)