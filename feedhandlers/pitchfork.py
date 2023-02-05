import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import cne, rss

import logging

logger = logging.getLogger(__name__)


def get_video_content(url, args, site_json, save_debug=False):
    video_html = utils.get_url_html(url)
    if not video_html:
        return None

    video_id = ''
    video_soup = BeautifulSoup(video_html, 'html.parser')
    for el in video_soup.find_all('iframe'):
        if el.has_attr('src'):
            m = re.search(r'\/cne-player\/player\.html\?autoplay=true&video=([0-9a-f]+)', el['src'])
            if m:
                video_id = m.group(1)
                break

    if not video_id:
        logger.warning('unable to find video id in ' + url)
        return None

    video_json = utils.get_url_json('https://player.cnevids.com/embed-api.json?videoId={}'.format(video_id))
    if not video_json:
        return None
    if save_debug:
        utils.write_file(video_json, './debug/debug.json')

    item = {}
    item['id'] = video_json['video']['id']
    item['url'] = url
    item['title'] = video_json['video']['title']

    dt = datetime.fromisoformat(video_json['video']['premiere_date'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = 'Pitchfork'

    item['tags'] = video_json['video']['tags'].copy()

    el = video_soup.find('meta', attrs={"name": "description"})
    if el and el.get('content'):
        item['summary'] = el['content']
        caption = el['content']
    else:
        caption = ''

    item['_image'] = video_json['video']['poster_frame']
    item['_image'] = re.sub(r',h_\d{2,4}', '', item['_image'])
    item['_image'] = re.sub(r'w_\d{2,4}', 'w_1000', item['_image'])

    def get_video(videos):
        for video_type in ['video/mp4', 'video/webm', 'application/x-mpegURL']:
            for video in videos:
                if video['type'] == video_type:
                    return video
        return None

    video = get_video(video_json['video']['sources'])
    if video:
        item['_video'] = video['src']
        item['content_html'] = utils.add_video(video['src'], video['type'], item['_image'], caption)
    return item


def get_review_content(url, args, site_json, save_debug=False):
    json_url = 'https://pitchfork.com/api/v2' + urlsplit(url).path
    review_json = utils.get_url_json(json_url)
    if not review_json:
        return None
    if save_debug:
        utils.write_file(review_json, './debug/debug.json')

    # Assume only 1
    result_json = review_json['results'][0]
    item = {}
    item['id'] = result_json['id']
    item['url'] = 'https://www.pitchfork.com' + result_json['url']
    item['title'] = result_json['title']

    dt = datetime.fromisoformat(result_json['pubDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = datetime.fromisoformat(result_json['modifiedAt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for author in result_json['authors']:
        authors.append(author['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if result_json.get('tags'):
        for tag in result_json['tags']:
            if isinstance(tag, dict):
                item['tags'].append(tag['name'])
            else:
                item['tags'].append(tag)
    if result_json.get('genres'):
        for tag in result_json['genres']:
            item['tags'].append(tag['display_name'])

    if result_json['photos'].get('lede'):
        item['_image'] = result_json['photos']['lede']['sizes']['standard']
    elif result_json['photos'].get('tout'):
        item['_image'] = result_json['photos']['tout']['sizes']['standard']
    elif result_json['photos'].get('social'):
        item['_image'] = result_json['photos']['social']['sizes']['standard']

    item['summary'] = result_json['promoDescription']

    if result_json['contentType'] == 'albumreview':
        # Assume only 1??
        album = result_json['tombstone']['albums'][0]
        artists = album['album']['artists']
        title = album['album']['display_name']
        photos = album['album']['photos']
        rating = album['rating']['display_rating']
    elif result_json['contentType'] == 'tracks':
        # Assume only 1??
        track = result_json['tracks'][0]
        artists = track['artists']
        title = track['display_name']
        photos = result_json['photos']
        rating = None

    artist_name = ''
    for artist in artists:
        if artist_name:
            artist_name += ' / '
        artist_name += artist['display_name']

    item['title'] = '{} by {}'.format(title, artist_name)

    if photos.get('tout'):
        img_src = photos['tout']['sizes']['standard']
    elif photos.get('lede'):
        img_src = photos['lede']['sizes']['standard']
    elif photos.get('social'):
        img_src = photos['social']['sizes']['standard']

    content_html = utils.add_image(img_src)
    content_html += '<center><h3 style="margin:0;">{}</h3><h2 style="margin:0;"><i>{}</i></h2>'.format(artist_name,
                                                                                                       title)
    if rating:
        content_html += '<h1 style="margin:0;">{}</h1>'.format(rating)
    content_html += '</center><p><i>{}</i></p>'.format(result_json['dek'])

    if result_json.get('audio_files'):
        for audio in result_json['audio_files']:
            audio_embed = utils.add_embed(audio['embedUrl'])
            content_html += audio_embed
    else:
        content_html += '<hr width="80%" />'

    soup = BeautifulSoup(result_json['body']['en'], 'html.parser')
    for el in soup.find_all('figure', class_='contents__embed'):
        if el.iframe and el.iframe.has_attr('src'):
            embed_html = utils.add_embed(el.iframe['src'])
            el.insert_after(BeautifulSoup(embed_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled embed in ' + url)
    item['content_html'] = content_html + str(soup)
    return item


def get_content(url, args, site_json, save_debug=False):
    if '/reviews/' in url:
        return get_review_content(url, args, site_json, save_debug)
    elif '/tv/' in url:
        return get_video_content(url, args, site_json, save_debug)
    return cne.get_content(url, args, site_json, save_debug)


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
