import html, math, re
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=980):
    split_url = urlsplit(img_src)
    return 'https://{}{}?w={}&q=75'.format(split_url.netloc, split_url.path, width)


def render_content(content, netloc, inc_gallery=False):
    content_html = ''
    if content['type'] == 'singlePostText':
        content_html += content['data']['text']

    elif content['type'] == 'singlePostImage' or content['type'] == 'articleThumbnail':
        if content['data'].get('url'):
            if content['data'].get('caption'):
                caption = content['data']['caption']
            else:
                caption = ''
            content_html += utils.add_image(resize_image(content['data']['url']), caption)

    elif content['type'] == 'singlePostOembed':
        if content['data']['provider_name'] == 'YouTube':
            content_html += utils.add_embed('https://www.youtube.com/embed/' + content['data']['videoId'])
        elif content['data']['provider_name'] == 'Twitter':
            content_html += utils.add_embed(content['data']['url'])
        elif content['data']['provider_name'] == 'Instagram':
            m = re.search(r'data-instgrm-permalink="([^"\?]+)', content['data']['html'])
            if m:
                content_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unable to find singlePostOembed Instagram embed url')
        elif content['data']['provider_name'] == 'TikTok':
            m = re.search(r'cite="([^"\?]+)', content['data']['html'])
            if m:
                content_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unable to find singlePostOembed TikTok embed url')
        elif content['data']['provider_name'] == 'Spotify':
            m = re.search(r'src="([^"\?]+)', content['data']['html'])
            if m:
                content_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unable to find singlePostOembed TikTok embed url')
        elif content['data']['provider_name'] == 'Polldaddy' or content['data']['provider_name'] == 'provider_unknown':
            m = re.search(r'iframe src="([^"\?]+)', content['data']['html'])
            if m:
                content_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled singlePostOembed ' + content['data']['provider_name'])
        else:
            logger.warning('unhandled singlePostOembed ' + content['data']['provider_name'])

    elif content['type'] == 'singlePostList':
        for item in content['data']['items']:
            if item.get('podContent'):
                content_html += '<h3>{}</h3>'.format(item['title'])
                if item.get('mediaPodContent'):
                    for item_content in item['mediaPodContent']:
                        content_html += render_content(item_content, netloc)
                for item_content in item['podContent']:
                    content_html += render_content(item_content, netloc)
            else:
                content_html += '<h2 style="margin-bottom:0;">{}</h2>'.format(item['title'])
                content_html += '<p style="margin-top:0;">{}</p>'.format(item['subtitle'])

    elif content['type'] == 'singlePostGallery':
        if inc_gallery:
            gallery_url = 'https://' + netloc + content['data']['url']
            gallery_json = utils.get_url_json(gallery_url)
            if gallery_json:
                if gallery_json['gallery'][0].get('gallery_api_url'):
                    gallery_url = 'https:' + gallery_json['gallery'][0]['gallery_api_url']
                    gallery_json = utils.get_url_json(gallery_url)
            if gallery_json:
                if False:
                    utils.write_file(gallery_json, './debug/gallery.json')
                if gallery_json['gallery'][0].get('title'):
                    content_html = '<h2>Gallery: {}</h2>'.format(gallery_json['gallery'][0]['title'])
                elif gallery_json['gallery'][0].get('post-title'):
                    content_html = '<h2>Gallery: {}</h2>'.format(gallery_json['gallery'][0]['post-title'])
                for photo in gallery_json['gallery'][0]['photo']:
                    content_html += utils.add_image(resize_image(photo['photo-url']), photo['photo-excerpt'])
                    content_html += '<h3>{}</h3>'.format(photo['photo-title'])
                    if photo['photo-description'].startswith('<'):
                        content_html += photo['photo-description']
                    else:
                        content_html += '<p>{}</p>'.format(photo['photo-description'])
                    content_html += '<br/><hr/><br/>'
                content_html = content_html[:-15]

    elif content['type'] == 'singlePostPodcastplayer':
        podcast_url = 'https://{}/rest/carbon/api/playlist/{}'.format(netloc, content['data']['id'])
        podcast_json = utils.get_url_json(podcast_url)
        if podcast_json:
            content_html += '<table style="width:90%; margin-left:auto; margin-right:auto;"><tr><td><img style="width:256px;" src="{}"/></td><td style="vertical-align:top;"><strong>{}</strong><br/><small>{}</small></td></tr></table>'.format(podcast_json['playlist']['playlistThumbnail'], podcast_json['playlist']['title'], podcast_json['playlist']['description'])
            play_button = '{}/static/play_button-48x48.png'.format(config.server)
            content_html += '<table style="width:90%; margin-left:auto; margin-right:auto;">'
            for i, it in enumerate(podcast_json['playlist']['items']):
                dt = datetime.fromisoformat(it['createdGmt'].replace('Z', '+00:00'))
                m = math.floor(int(it['duration'])/60)
                duration = '{} min'.format(m)
                if m >= 60:
                    hr = math.floor(int(it['duration'])/3600)
                    duration = '{} hr'.format(hr)
                    m = math.floor((int(it['duration']) - 3600*hr)/60)
                    if m > 0:
                        duration += ', {} min'.format(m)
                content_html += '<tr><td style="vertical-align:middle;"><a href="{}"><img src="{}"/></a></td><td><small>{} &bull; {}</small><br/>{}</td></tr>'.format(it['url'], play_button, utils.format_display_date(dt, False), duration, it['title'])
                if i == 4:
                    break
            content_html += '</table>'

    elif re.search(r'singlePost(Brandedapppromo|InArticleAd|Newsletter)', content['type']):
        pass

    else:
        logger.warning('unhandled content type ' + content['type'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    api_url = 'https://{}/rest/carbon/filter/main{}'.format(split_url.netloc, split_url.path)
    api_json = utils.get_url_json(api_url)

    item = {}
    item['id'] = api_json['options']['postId']
    article_json = api_json['widgets']['carbonwidget/single-1']['dataDetails'][str(item['id'])]
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item['url'] = article_json['url']
    item['title'] = html.unescape(article_json['title'])

    dt = datetime.fromisoformat(article_json['postDateGmt'].replace(' +0000', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['postModifiedGmt'].replace(' +0000', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['authors']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for it in article_json['categories']:
        item['tags'].append(it['title'])
    if article_json.get('tags'):
        for it in article_json['tags']:
            item['tags'].append(it['title'])
    if not item.get('tags'):
        del item['tags']

    item['_image'] = 'https:' + article_json['thumbnail']
    item['summary'] = article_json['excerpt']

    n = 0
    item['content_html'] = ''
    for content in article_json['podHeader']+article_json['podContent']:
        inc_gallery = False
        if content['type'] == 'singlePostGallery' and n == 0 and ('Galleries' in item['tags'] or 'Lists' in item['tags']):
            inc_gallery = True
            n += 1
        item['content_html'] += render_content(content, split_url.netloc, inc_gallery)

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
