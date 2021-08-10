import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

from feedhandlers import bandcamp, cne, rss, soundcloud
import utils

import logging
logger = logging.getLogger(__name__)

def get_content_review(url, args, save_debug=False):
  json_url = 'https://pitchfork.com/api/v2' + urlsplit(url).path
  review_json = utils.get_url_json(json_url)
  if not review_json:
    return None
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(review_json, file, indent=4)

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

  # Check age
  if 'age' in args:
    if not utils.check_age(item, args):
      return None

  authors = []
  for author in result_json['authors']:
    authors.append(author['name'])
  if authors:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  if result_json.get('tags'):
    item['tags'] = result_json['tags'].copy()
  if result_json.get('genres'):
    if item.get('tags'):
      for genre in result_json['genres']:
        item['tags'].append(genre['display_name'])

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
  content_html += '<center><h3 style="margin:0;">{}</h3><h2 style="margin:0;"><i>{}</i></h2>'.format(artist_name, title)
  if rating:
    content_html += '<h1 style="margin:0;">{}</h1>'.format(rating)
  content_html += '</center><p>{}</p><hr width="80%" />'.format(result_json['dek'])

  if result_json.get('audio_files'):
    for audio in result_json['audio_files']:
      audio_embed = ''
      if 'bandcamp' in audio['embedUrl']:
        audio_embed = bandcamp.get_content(audio['embedUrl'], None, save_debug)
      elif 'soundcloud' in audio['embedUrl']:
        audio_embed = soundcloud.get_content(audio['embedUrl'], None, save_debug)
      if audio_embed:
        content_html += audio_embed['content_html'] + '<hr width="80%" />'

  soup = BeautifulSoup(result_json['body']['en'], 'html.parser')
  for el in soup.find_all('figure', class_='contents__embed'):
    if el.iframe and el.iframe.has_attr('src'):
      if re.search(r'youtu\.?be', el.iframe['src']):
        new_el = utils.add_youtube(el.iframe['src'])
        el.insert_after(BeautifulSoup(new_el, 'html.parser'))
        el.decompose()
    else:
      logger.warning('unhandled embed in ' + url)
  item['content_html'] = content_html + str(soup)
  return item

def get_content(url, args, save_debug=False):
  if 'pitchfork.com/reviews' in url:
    return get_content_review(url, args, save_debug)
  return cne.get_content(url, args, save_debug)

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)