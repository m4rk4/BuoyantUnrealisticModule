import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    gql_query = {
        "operationName": "Post",
        "variables": {
            "id": paths[-1],
            "idType": "SLUG"
        },
        "query": "\n  query Post($id: ID!, $idType: PostIdType) {\n    post(id: $id, idType: $idType) {\n      ...ArticleFields\n      seoSetting {\n        ...SeoFields\n      }\n    }\n  }\n  \n  fragment ArticleFields on Post {\n    eetPostId\n    id\n    databaseId\n    dateGmt\n    uri\n    link\n    excerpt(format: RENDERED)\n    tags {\n      edges {\n        node {\n          name\n        }\n      }\n    }\n    creators {\n      nodes {\n        ...MinimalCreatorFields\n      }\n    }\n    tags {\n      nodes {\n        name\n      }\n    }\n    ntdImage352220\n    ntdImage1200630\n    ntdLegacySocialImage\n    featuredImage {\n      node {\n        mediaItemUrl\n        sourceUrl(size: POST_THUMBNAIL)\n        caption(format: RENDERED)\n      }\n    }\n    featuredVideoCaption\n    title\n    content\n    isVideo\n    isLiveVideo\n    teaserVideoUrl\n    teaserVideoM3u8\n    featuredVideoID\n    featuredVideoM3u8\n    teaserVideoID\n    ...PrimaryCategoryFields\n    liveChatStatus\n    liveStatus\n    liveStartTime\n    liveEndTime\n    liveStartDateYear\n    liveType\n    modifiedGmt\n    dateGmt\n    categories(first: 1) {\n      edges {\n        node {\n          name\n        }\n      }\n    }\n    noAds\n    isPremium\n    countries\n    terms(first: 100) {\n      nodes {\n        ...TermFields\n      }\n    }\n  }\n\n  fragment SeoFields on SeoObject {\n    lsg_canonical_url\n    lsg_fb_description\n    lsg_fb_image\n    lsg_fb_title\n    lsg_meta_description\n    lsg_meta_keywords\n    lsg_meta_title\n    lsg_robot_nofollow\n    lsg_robot_noindex\n  }\n\n  fragment MinimalCreatorFields on Creator {\n    databaseId\n    name\n    uri\n    avatarUrl\n    parent {\n      node {\n        name\n      }\n    }\n  }\n\n  fragment PrimaryCategoryFields on Post {\n    primaryTerm {\n      databaseId\n      description\n      link\n      name\n      slug\n      taxonomy\n      uri\n    }\n  }\n\n  fragment TermFields on TermNode {\n    databaseId\n    name\n    slug\n    taxonomyName\n  }\n"
    }
    gql_json = utils.post_url('https://wp1.ntd.com/graphql', json_data=gql_query)
    if not gql_json:
        return None
    post_json = gql_json['data']['post']
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['link']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['dateGmt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if post_json.get('modifiedGmt'):
        dt = datetime.fromisoformat(post_json['modifiedGmt'])
        item['date_modified'] = dt.isoformat()

    if post_json.get('creators') and post_json['creators'].get('nodes'):
        authors = []
        for it in post_json['creators']['nodes']:
            authors.append(it['name'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if post_json.get('terms') and post_json['terms'].get('nodes'):
        for it in post_json['terms']['nodes']:
            item['tags'].append(it['name'])
    if post_json.get('tags') and post_json['tags'].get('nodes'):
        for it in post_json['tags']['nodes']:
            if it['name'] not in item['tags']:
                item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']

    item['content_html'] = ''
    if post_json.get('featuredImage') and post_json['featuredImage'].get('node'):
        item['_image'] = post_json['featuredImage']['node']['sourceUrl']
        item['content_html'] = utils.add_image(item['_image'], post_json['featuredImage']['node'].get('caption'))

    if post_json.get('featuredVideoID'):
        video_src = ''
        poster = item['_image']
        captions = []
        video_json = utils.get_url_json('https://www.youmaker.com/v1/api/video/metadata/' + post_json['featuredVideoID'])
        if video_json:
            utils.write_file(video_json, './debug/video.json')
            if video_json['data']['data'].get('videoAssets'):
                video_src = 'https:' + video_json['data']['data']['videoAssets']['Stream']
            if video_json['data'].get('thumbmail_path'):
                poster = 'https:' + video_json['data']['thumbmail_path']
            if video_json['data'].get('title'):
                captions.append(video_json['data']['title'])
            if video_json['data'].get('credit'):
                captions.append(video_json['data']['credit'])
        if not video_src and post_json.get('featuredVideoM3u8'):
            video_src = post_json['featuredVideoM3u8']
        if video_src:
            item['content_html'] = utils.add_video(video_src, 'application/x-mpegURL', poster, ' | '.join(captions))
        else:
            logger.warning('unhandled featuredVideo in ' + item['url'])

    item['content_html'] += wp_posts.format_content(post_json['content'], item, site_json)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        category = 'news'
    else:
        category = paths[-1]

    gql_query = {
        "operationName": "get_posts_by_category_slug",
        "variables": {
            "id": category,
            "idType": "SLUG",
            "first": 10,
        },
        "query":"fragment MinimalCreatorFields on Creator {\n  databaseId\n  name\n  uri\n  avatarUrl\n  parent {\n    node {\n      name\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment CatPostListFields on Post {\n  id\n  isVideo\n  databaseId\n  title\n  excerpt\n  uri\n  link\n  date\n  dateGmt\n  liveStartDateYear\n  ntdImage630400\n  ntdImage352220\n  ntdImagemediumvertical\n  featuredImage {\n    node {\n      mediaItemUrl\n      __typename\n    }\n    __typename\n  }\n  creators {\n    nodes {\n      ...MinimalCreatorFields\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment SeoFields on SeoObject {\n  lsg_canonical_url\n  lsg_fb_description\n  lsg_fb_image\n  lsg_fb_title\n  lsg_meta_description\n  lsg_meta_keywords\n  lsg_meta_title\n  lsg_robot_nofollow\n  lsg_robot_noindex\n  __typename\n}\n\nquery get_posts_by_category_slug($id: ID!, $first: Int, $after: String, $idType: CategoryIdType = SLUG) {\n  category(id: $id, idType: $idType) {\n    id\n    name\n    slug\n    uri\n    parentId\n    count\n    databaseId\n    description\n    taxonomyName\n    posts(first: $first, after: $after) {\n      nodes {\n        ...CatPostListFields\n        __typename\n      }\n      pageInfo {\n        endCursor\n        hasNextPage\n        __typename\n      }\n      __typename\n    }\n    seoSetting {\n      ...SeoFields\n      __typename\n    }\n    __typename\n  }\n}"
    }
    gql_json = utils.post_url('https://wp1.ntd.com/graphql', json_data=gql_query)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')
    posts = gql_json['data']['category']['posts']

    n = 0
    feed_items = []
    for post in posts['nodes']:
        if save_debug:
            logger.debug('getting content for ' + post['link'])
        item = get_content(post['link'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    # feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
