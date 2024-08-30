import pytz, re
from bs4 import BeautifulSoup
from curl_cffi import requests
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    if '/magazine/' in url:
        return wp_posts.get_content(url, args, site_json, save_debug)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    gql_query = {
        "operationName": "ArticleQuery",
        "query": "query ArticleQuery($short: String, $slug: String!, $relatedLength: Int) {\n  locale(short: $short) {\n    post(slug: $slug) {\n      id\n      deletedAt\n      slug\n      views\n      pixelUrl\n      postOptions {\n        hideDisclaimer\n        isPromo\n      }\n      alternates {\n        id\n        short\n        domain\n        code\n      }\n      postTranslate {\n        id\n        title\n        leadText\n        twitterLeadText\n        facebookLeadText\n        bodyText\n        description\n        socialDescription\n        avatar\n        author {\n          id\n          slug\n          avatar\n          gender\n          innovationCircleUrl\n          authorTranslates {\n            id\n            name\n          }\n        }\n        youtube\n        audio\n        editorsPriority\n        published\n        publishedHumanFormat\n        facebookShares\n        twitterShares\n        redditShares\n        totalShares\n        noIndex\n      }\n      author {\n        id\n        slug\n        avatar\n        gender\n        innovationCircleUrl\n        authorTranslates {\n          id\n          name\n        }\n      }\n      postBadge {\n        id\n        label\n        postBadgeTranslates {\n          id\n          title\n        }\n      }\n      category {\n        id\n        slug\n        categoryTranslates {\n          id\n          title\n        }\n      }\n      tags {\n        id\n        slug\n        tagTranslates {\n          id\n          title\n        }\n      }\n      topics {\n        selection\n        post {\n          id\n          views\n          slug\n          category {\n            id\n          }\n          postTranslate {\n            id\n            title\n            leadText\n            published\n            avatar\n            author {\n              id\n              slug\n              avatar\n              gender\n              innovationCircleUrl\n              authorTranslates {\n                id\n                name\n              }\n            }\n          }\n        }\n      }\n      relatedPosts(length: $relatedLength) {\n        id\n        slug\n        category {\n          id\n        }\n        postTranslate {\n          avatar\n          title\n          author {\n            id\n            slug\n            avatar\n            gender\n            innovationCircleUrl\n            authorTranslates {\n              id\n              name\n            }\n          }\n        }\n      }\n      showShares\n      showStats\n    }\n  }\n}\n",
        "variables": {
            "slug": paths[-1]
        }
    }
    r = requests.post('https://conpletus.cointelegraph.com/v1/', json=gql_query, impersonate=config.impersonate)
    if r.status_code != 200:
        return None
    gql_json = r.json()
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    post_json = gql_json['data']['locale']['post']
    item = {}
    item['id'] = post_json['id']
    item['url'] = url
    item['title'] = post_json['postTranslate']['title']

    dt = datetime.fromisoformat(post_json['postTranslate']['published'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": post_json['author']['authorTranslates'][0]['name']}

    if post_json.get('tags'):
        item['tags'] = []
        for it in post_json['tags']:
            item['tags'].append(it['tagTranslates'][0]['title'])

    item['content_html'] = ''
    if post_json['postTranslate'].get('leadText'):
        item['content_html'] += '<p><em>' + post_json['postTranslate']['leadText'] + '</em></p>'

    if post_json['postTranslate'].get('avatar'):
        item['_image'] = post_json['postTranslate']['avatar']
        item['content_html'] += utils.add_image(item['_image'])

    if post_json['postTranslate'].get('description'):
        item['summary'] = post_json['postTranslate']['description']

    if 'embed' in args:
        item['content_html'] = '<div style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0; border:1px solid black; border-radius:10px;"><a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a><div style="margin-left:8px; margin-right:8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['_image'], split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}" target="_blank">Read</a></p></div></div><div>&nbsp;</div>'.format(config.server, quote_plus(item['url']))
        return item

    if post_json['postTranslate'].get('audio'):
        item['content_html'] += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen to article</a></span></div><div>&nbsp;</div>'.format(post_json['postTranslate']['audio'], config.server)

    soup = BeautifulSoup(post_json['postTranslate']['bodyText'])
    for el in soup.find_all(attrs={"data-ct-story-hidden": True}):
        el.decompose()

    for el in soup.select('p:has(> strong:has(> em:-soup-contains("Related:")))'):
        el.decompose()

    for el in soup.select('figure:has(> img)'):
        it = el.find('figcaption')
        if it:
            caption = it.decode_contents()
        else:
            caption = ''
        new_html = utils.add_image(el.img['src'], caption)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.select('p:has(> img)'):
        it = el.find_next_sibling()
        if it and it.name == 'p' and it.get('style') and re.search(r'text-align:\s?center', it['style']):
            caption = it.get_text()
            it.decompose()
        else:
            caption = ''
        new_html = utils.add_image(el.img['src'], caption)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='twitter-tweet'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('blockquote', class_=False):
        new_html = utils.add_blockquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('p', class_='post-content__accent'):
        new_html = '<div>&nbsp;</div><div style="width:80%; margin-left:auto; margin-right:auto; text-align:center;"><span style="display:inline-block; min-width:180px; text-align:center; padding:0.5em; font-size:0.8em; font-weight:bold; color:black; background-color:#ccc; border:1px solid #ccc;">{}</span></div><div>&nbsp;</div>'.format(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(['script', 'template']):
        el.decompose()

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
