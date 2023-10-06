import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_graphql_data(data):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "authorization": "Bearer tlqhsdKW5Eylsyo5unxzZROdnuzAztTBS1g1xn5vMU4",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"116\", \"Not)A;Brand\";v=\"24\", \"Microsoft Edge\";v=\"116\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.81"
    }
    return utils.post_url('https://graphql.contentful.com/content/v1/spaces/56u5qdsjym8c/environments/master', json_data=data, headers=headers)


def resize_image(img_src, width=1000):
    return utils.clean_url(img_src) + '?fl=progressive&q=80&w={}'.format(width)


def render_content(content, body_links):
    content_html = ''
    if content['nodeType'] == 'text':
        start_tag = ''
        end_tag = ''
        for it in content['marks']:
            if it['type'] == 'bold':
                start_tag += '<b>'
                end_tag = '</b>' + end_tag
            elif it['type'] == 'italic':
                start_tag += '<i>'
                end_tag = '</i>' + end_tag
            elif it['type'] == 'underline':
                start_tag += '<u>'
                end_tag = '</u>' + end_tag
            else:
                logger.warning('unhandled mark type ' + it['type'])
        content_html += start_tag + content['value'] + end_tag
    elif content['nodeType'] == 'paragraph':
        content_html += '<p>'
        for c in content['content']:
            content_html += render_content(c, body_links)
        content_html += '</p>'
    elif content['nodeType'] == 'hyperlink':
        content_html += '<a href="{}">'.format(content['data']['uri'])
        for c in content['content']:
            content_html += render_content(c, body_links)
        content_html += '</a>'''
    elif content['nodeType'] == 'heading-5':
        content_html += '<h3>'
        for c in content['content']:
            content_html += render_content(c, body_links)
        content_html += '</h3>'
    elif content['nodeType'] == 'unordered-list':
        content_html += '<ul>'
        for c in content['content']:
            content_html += render_content(c, body_links)
        content_html += '</ul>'
    elif content['nodeType'] == 'list-item':
        content_html += '<li>'
        for c in content['content']:
            content_html += render_content(c, body_links)
        content_html += '</li>'
    elif content['nodeType'] == 'hr':
        content_html += '<hr/>'
    elif content['nodeType'] == 'embedded-asset-block':
        data = {
            "operationName": "Asset",
            "variables": {
                "id": content['data']['target']['sys']['id']
            },
            "query": "query Asset($id: String!) {\n  asset(id: $id) {\n    contentType\n    url\n    description\n    height\n    title\n    width\n    __typename\n  }\n}\n"
        }
        asset_data = get_graphql_data(data)
        # utils.write_file(asset_data, './debug/asset.json')
        if asset_data and asset_data.get('data') and asset_data['data'].get('asset'):
            asset = asset_data['data']['asset']
            if asset['contentType'] == 'image/jpeg' or asset['contentType'] == 'image/png':
                content_html += utils.add_image(resize_image(asset['url']), asset.get('description'))
            else:
                logger.warning('unhandled asset contentType ' + asset['contentType'])
        else:
            logger.warning('unhandled embedded-asset-block id ' + content['data']['target']['sys']['id'])
    elif content['nodeType'] == 'embedded-entry-block':
        entry = next((it for it in body_links['entries']['block'] if it['sys']['id'] == content['data']['target']['sys']['id']), None)
        if entry:
            if entry['__typename'] == 'EmbedSocial':
                data = {
                    "operationName": "EmbedSocial",
                    "variables": {
                        "id": entry['sys']['id']
                    },
                    "query": "\nquery EmbedSocial($id: String!) {\n  embedSocial(id: $id) {\n    \n  title\n  socialMediaType\n  socialContent\n\n  }\n}\n"
                }
                entry_data = get_graphql_data(data)
                #utils.write_file(entry_data, './debug/asset.json')
                if entry_data and entry_data.get('data') and entry_data['data'].get('embedSocial'):
                    soup = BeautifulSoup(entry_data['data']['embedSocial']['socialContent'], 'html.parser')
                    if soup.find(class_='twitter-tweet'):
                        links = soup.find_all('a')
                        content_html += utils.add_embed(links[-1]['href'])
                    elif soup.find(class_='instagram-media'):
                        el = soup.find(attrs={"data-instgrm-permalink": True})
                        content_html += utils.add_embed(el['data-instgrm-permalink'])
                    else:
                        logger.warning('unhandled embedSocial content ' + entry_data['data']['embedSocial']['socialContent'])
            elif entry['__typename'] == 'PullQuote':
                data = {
                    "operationName": "PullQuote",
                    "variables": {
                        "id": entry['sys']['id']
                    },
                    "query": "\nquery PullQuote($id: String!) {\n  pullQuote(id: $id) {\n    \n  text\n  attribution\n  hideQuote\n\n  }\n}\n"
                }
                entry_data = get_graphql_data(data)
                #utils.write_file(entry_data, './debug/asset.json')
                if entry_data and entry_data.get('data') and entry_data['data'].get('pullQuote'):
                    content_html += utils.add_pullquote(entry_data['data']['pullQuote']['text'], entry_data['data']['pullQuote']['attribution'])
            elif entry['__typename'] == 'RecommendedArticles':
                pass
            else:
                logger.warning('unhandled embedded-entry-block type ' + entry['__typename'])
        else:
            logger.warning('unhandled embedded-entry-block id ' + content['data']['target']['sys']['id'])
    else:
        logger.warning('unhandled content nodeType ' + content['nodeType'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    story_json = None
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    data = {
        "operationName": "BySlug",
        "variables": {
            "slug": paths[-1]
        },
        "query": "query BySlug($slug: String, $preview: Boolean) {\n  storyCollection(limit: 1, preview: $preview, where: {slug: $slug}) {\n    total\n    items {\n      title\n      headline\n      slug\n      cat {\n        category\n        series\n        __typename\n      }\n      audience\n      author\n      body {\n        json\n        links {\n          entries {\n            hyperlink {\n              __typename\n              ... on Story {\n                slug\n                sys {\n                  id\n                  __typename\n                }\n                __typename\n              }\n              ... on Event {\n                slug\n                sys {\n                  id\n                  __typename\n                }\n                __typename\n              }\n              ... on Tour {\n                slug\n                sys {\n                  id\n                  __typename\n                }\n                __typename\n              }\n              ... on Page {\n                slug\n                sys {\n                  id\n                  __typename\n                }\n                __typename\n              }\n            }\n            inline {\n              __typename\n              ... on Story {\n                slug\n                __typename\n              }\n              ... on Event {\n                slug\n                __typename\n              }\n            }\n            block {\n              __typename\n              sys {\n                id\n                __typename\n              }\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      sys {\n        publishedAt\n        firstPublishedAt\n        __typename\n      }\n      image {\n        contentType\n        url\n        description\n        height\n        title\n        width\n        __typename\n      }\n      video {\n        contentType\n        url\n        description\n        height\n        title\n        width\n        __typename\n      }\n      heroVideoEmbed {\n        provider\n        id\n        __typename\n      }\n      heroSource\n      heroCaption\n      tagsCollection {\n        items {\n          label\n          __typename\n        }\n        __typename\n      }\n      person {\n        name\n        image {\n          url\n          __typename\n        }\n        position\n        organization\n        youtube\n        coachId\n        email\n        shortBio\n        location\n        memberType\n        __typename\n      }\n      summary\n      recommended {\n        headline\n        articlesCollection {\n          total\n          items {\n            headline\n            slug\n            cat {\n              category\n              series\n              __typename\n            }\n            summary\n            sys {\n              id\n              publishedAt\n              firstPublishedAt\n              __typename\n            }\n            image {\n              description\n              url\n              width\n              height\n              __typename\n            }\n            video {\n              contentType\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      related {\n        headline\n        linksCollection {\n          items {\n            headline\n            slug\n            cat {\n              category\n              series\n              __typename\n            }\n            summary\n            sys {\n              id\n              publishedAt\n              firstPublishedAt\n              __typename\n            }\n            image {\n              description\n              url\n              width\n              height\n              __typename\n            }\n            video {\n              contentType\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
    }
    gql_data = get_graphql_data(data)
    if gql_data:
        if save_debug:
            utils.write_file(gql_data, './debug/debug.json')
        story_json = gql_data['data']['storyCollection']['items'][0]
    else:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if save_debug:
                utils.write_file(next_data, './debug/next.json')
            for key, val in next_data['props']['apolloState'].items():
                if key.startswith('storyCollection'):
                    story_json = val['items'][0]
                    break
    if not story_json:
        return None

    item = {}
    item['id'] = story_json['slug']
    item['url'] = url
    item['title'] = story_json['title']

    dt = datetime.fromisoformat(story_json['sys']['firstPublishedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(story_json['sys']['publishedAt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    if story_json.get('author'):
        item['author'] = {"name": story_json['author']}
    else:
        item['author'] = {"name": "PGA of America"}

    item['tags'] = []
    if story_json.get('cat'):
        if story_json['cat'].get('category'):
            item['tags'].append(story_json['cat']['category'])
        if story_json['cat'].get('series'):
            item['tags'].append(story_json['cat']['series'])
    if story_json.get('tagsCollection') and story_json['tagsCollection'].get('items'):
        for it in story_json['tagsCollection']['items']:
            item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    if story_json.get('summary'):
        item['summary'] = story_json['summary']

    item['content_html'] = ''
    if story_json.get('image'):
        item['_image'] = story_json['image']['url']
        captions = []
        if story_json.get('heroCaption'):
            captions.append(story_json['heroCaption'])
        if story_json.get('heroSource'):
            captions.append(story_json['heroSource'])
        item['content_html'] += utils.add_image(resize_image(item['_image']), ' | '.join(captions))

    for content in story_json['body']['json']['content']:
        item['content_html'] += render_content(content, story_json['body']['links'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'stories' not in paths:
        logger.warning('unhandled feed url ' + url)
        return None

    data = {
        "operationName": "Stories",
        "variables": {
            "limit": 12
        },
        "query": "query Stories($skip: Int, $limit: Int, $series: String) {\n  storyCollection(limit: $limit, skip: $skip, where: {series: $series}, order: [sys_firstPublishedAt_DESC]) {\n    total\n    items {\n      headline\n      slug\n      cat {\n        category\n        series\n        __typename\n      }\n      summary\n      sys {\n        id\n        publishedAt\n        firstPublishedAt\n        __typename\n      }\n      image {\n        description\n        url\n        width\n        height\n        __typename\n      }\n      video {\n        contentType\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  storiesPageCollection(limit: 1) {\n    items {\n      metaTitleAll\n      metaDescriptionAll\n      metaImageAll {\n        url\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
    }
    gql_data = get_graphql_data(data)
    if not gql_data:
        return None
    if save_debug:
        utils.write_file(gql_data, './debug/feed.json')

    n = 0
    feed_items = []
    for story in gql_data['data']['storyCollection']['items']:
        story_url = 'https://www.pga.com/story/' + story['slug']
        if save_debug:
            logger.debug('getting content for ' + story_url)
        item = get_content(story_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = 'Stories - PGA of America'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
