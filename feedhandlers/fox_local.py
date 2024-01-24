import base64, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://api.fox29.com/fts/prod//articles?spark_id=07334621-1c90-5fa1-9d1e-7f8007f567b2
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('meta', attrs={"name": "fox.page_content_id"})
    if not el:
        logger.warning('unable to determine fox.page_content_id in ' + url)
        return None

    if 'video' in paths:
        api_url = '{}/videos?spark_id={}'.format(site_json['api_url'], el['content'])
    else:
        api_url = '{}/articles?spark_id={}'.format(site_json['api_url'], el['content'])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    return get_article_content(api_json['data']['results'][0], args, site_json, save_debug)


def get_article_content(article_json, args, site_json, save_debug=False):
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')
    item = {}
    item['id'] = article_json['spark_id']
    item['url'] = 'https://' + article_json['canonical_url']
    item['title'] = article_json['title']

    if article_json['publication_date'].endswith('Z'):
        dt = datetime.fromisoformat(article_json['publication_date'].replace('Z', '+00:00'))
    else:
        dt = datetime.fromisoformat(article_json['publication_date']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('last_modified_date'):
        if article_json['last_modified_date'].endswith('Z'):
            dt = datetime.fromisoformat(article_json['last_modified_date'].replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(article_json['last_modified_date']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('fn__additional_authors'):
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(article_json['fn__additional_authors']))
    elif article_json.get('fn__persons'):
        authors = []
        for it in article_json['fn__persons']:
            authors.append(it['full_name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('source'):
        item['author']['name'] = article_json['source']['label']

    item['tags'] = []
    if article_json.get('category'):
        item['tags'].append(article_json['category']['title'])
    if article_json.get('fn__tags'):
        for it in article_json['fn__tags']:
            if it.get('title') and it['title'] not in item['tags']:
                item['tags'].append(it['title'])
    if article_json.get('local__tags'):
        for it in article_json['local__tags']:
            if it.get('title') and it['title'] not in item['tags']:
                item['tags'].append(it['title'])
    if article_json.get('tags'):
        for it in article_json['tags']:
            if it.get('title') and it['title'] not in item['tags']:
                item['tags'].append(it['title'])
    if not item.get('tags'):
        del item['tags']

    if article_json.get('fn__image'):
        item['_image'] = article_json['fn__image']['url']

    item['content_html'] = ''
    if article_json.get('dek'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['dek'])

    if article_json['component_type'] == 'video':
        item['content_html'] += utils.add_video(article_json['playback_url'], 'application/x-mpegURL', article_json['snapshot']['content']['url'])
        if article_json.get('description'):
            item['content_html'] += '<p>{}</p>'.format(article_json['description'])
    else:
        item['content_html'] += render_components(article_json['components'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def render_components(components):
    skip_list = False
    n = len(components)
    component_html = ''
    for i, component in enumerate(components):
        if component['content_type'] == 'text':
            # Skip related/suggested content
            if component['content']['text'].startswith('<p><strong>RELATED:</strong>'):
                continue
            elif component['content']['text'].startswith('<p><strong>SUGGESTED:</strong>') and i+1 < n and components[i+1]['content_type'] == 'list':
                skip_list = True
                continue
            component_html += component['content']['text']
        elif component['content_type'] == 'heading':
            component_html += '<h{0}>{1}</h{0}>'.format(component['content']['rank'], component['content']['text'])
        elif component['content_type'] == 'image':
            captions = []
            if component['content'].get('caption').strip():
                captions.append(component['content']['caption'].strip())
            if component['content'].get('copyright').strip():
                captions.append(component['content']['copyright'].strip())
            component_html += utils.add_image(component['content']['url'], ' | '.join(captions))
        elif component['content_type'] == 'image_gallery':
            for it in component['content']['images']:
                captions = []
                if it.get('caption').strip():
                    captions.append(it['caption'].strip())
                if it.get('copyright').strip():
                    captions.append(it['copyright'].strip())
                component_html += utils.add_image(it['url'], ' | '.join(captions))
        elif component['content_type'] == 'akta_video':
            component_html += utils.add_video(component['content']['media_url'], 'application/x-mpegURL', component['content']['snapshot'], component['content'].get('description'))
        elif component['content_type'] == 'live_video':
            key_json = {
                "v": component['content']['live_id'],
                "token": component['content']['token'],
                "accessKey": component['content']['access_key']
            }
            key = base64.b64encode(json.dumps(key_json, separators=(',', ':')).encode())
            lura_url = 'https://w3.mp.lura.live/player/prod/v3/anvload.html?key=' + key.decode()
            component_html += utils.add_embed(lura_url)
        elif component['content_type'] == 'twitter_tweet' or component['content_type'] == 'instagram_media' or component['content_type'] == 'facebook_post' or component['content_type'] == 'youtube_video' or component['content_type'] == 'tiktok_video':
            component_html += utils.add_embed(component['content']['url'])
        elif component['content_type'] == 'pdf':
            component_html += utils.add_embed('https://docs.google.com/gview?url=' + quote_plus(component['content']['url']))
        elif component['content_type'] == 'pull_quote':
            component_html += utils.add_pullquote(component['content']['text'], component['content'].get('credit'))
        elif component['content_type'] == 'list':
            if skip_list:
                skip_list = False
                continue
            if component['content']['ordered']:
                tag = 'ol'
            else:
                tag = 'ul'
            component_html += '<{}>'.format(tag)
            component_html += render_components(component['content']['items'])
            component_html += '</{}>'.format(tag)
        elif component['content_type'] == 'list_item':
            component_html += '<li>' + component['content']['title'] + '</li>'
        elif component['content_type'] == 'article':
            component_html += '<div style="width:90%; max-width:540px; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px;">'
            if component['content'].get('thumbnail'):
                component_html += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(component['content']['url'], component['content']['thumbnail'])
            component_html += '<div style="padding:8px;"><div style="font-size:1.1em; font-weight:bold;"><a href="http://{}">{}</a></div>'.format(component['content']['url'], component['content']['title'])
            if component['content'].get('dek'):
                component_html += '<p>{}</p>'.format(component['content']['dek'])
            component_html += '</div></div>'
        elif component['content_type'] == 'credible':
            # These are ad widgets for credible.com
            pass
        else:
            logger.warning('unhandled content type ' + component['content_type'])
    return component_html


def get_feed(url, args, site_json, save_debug=False):
    # https://api.fox29.com/fts/prod/trending/all
    # https://api.fox29.com/fts/prod/article
    tags = {
        "entertainment": "90831a27-019c-5a0f-8380-3971694207cc",
        "news": "d829cb67-c349-552f-a73b-9dfb4f744e8f",
        "sports": "08b18422-0ca2-5ed5-a64c-9cca9069f885"
    }
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        articles_json = utils.get_url_json('{}/articles'.format(site_json['api_url']))
        videos_json = utils.get_url_json('{}/videos'.format(site_json['api_url']))
    elif len(paths) == 1:
        articles_json = utils.get_url_json('{}/articles?tags=fts/{}'.format(site_json['api_url'], paths[0]))
        videos_json = utils.get_url_json('{}/videos?tags=fts/{}'.format(site_json['api_url'], paths[0]))
    elif paths[0] == 'tag':
        articles_json = utils.get_url_json('{}/articles?tags=fts/{}'.format(site_json['api_url'], '/'.join(paths[1:])))
        videos_json = utils.get_url_json('{}/videos?tags=fts/{}'.format(site_json['api_url'], '/'.join(paths[1:])))
    else:
        logger.warning('unsupported feed url ' + url)
        return None

    if not articles_json and not videos_json:
        return None
    if save_debug:
        utils.write_file(articles_json, './debug/feed.json')

    n = 0
    feed_items = []
    if articles_json:
        for article in articles_json['data']['results']:
            article_url = 'https://' + article['canonical_url']
            if save_debug:
                logger.debug('getting content for ' + article_url)
            item = get_article_content(article, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
    if videos_json:
        for video in videos_json['data']['results']:
            video_url = 'https://' + video['canonical_url']
            if save_debug:
                logger.debug('getting content for ' + video_url)
            item = get_article_content(video, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    feed = utils.init_jsonfeed(args)
    #feed['title'] = 'Stories - PGA of America'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed