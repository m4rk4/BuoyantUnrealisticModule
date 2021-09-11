import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, unquote_plus

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  split_url = urlsplit(url)
  netloc = re.sub(r'^([^\.]+)', 'www', split_url.netloc)
  path = split_url.path.split('/')
  json_url = 'https://{}/ajax/content-api/posts/{}'.format(netloc, path[-1])
  content_json = utils.get_url_json(json_url)
  if not content_json:
    return None
  if save_debug:
    utils.write_file(content_json, './debug/content.json')

  item = {}
  item['id'] = content_json['id']
  item['url'] = content_json['links']['site']
  item['title'] = content_json['attributes']['title']

  dt = datetime.fromisoformat(content_json['attributes']['published'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(content_json['attributes']['modified'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  authors = []
  for author in content_json['relationships']['authors']['data']:
    authors.append(author['attributes']['label'])
  if authors:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  if content_json['attributes'].get('categories'):
    item['tags'] = content_json['attributes']['categories'].copy()
  elif content_json['relationships']['categories'].get('data'):
    item['tags'] = []
    for tag in content_json['relationships']['categories']['data']:
      item['tags'].append(tag['attributes']['label'])

  if content_json['relationships']['images'].get('data'):
    item['_image'] = content_json['relationships']['images']['data'][0]['links']['self']

  item['summary'] = content_json['attributes']['description']

  content_html = content_json['attributes']['content']

  if content_json['attributes']['format'] == 'slideshow':
    for slide in content_json['relationships']['slides']['data']:
      if slide['type'] == 'slide':
        content_html += '<h3>{}</h3>'.format(slide['attributes']['title'])
        if slide['relationships'].get('image') and slide['relationships']['image'].get('data'):
          img_src = slide['relationships']['image']['data']['links']['self'] + '?width=1000&format=jpeg&auto=webp'
          captions = []
          caption = slide['relationships']['image']['data']['attributes'].get('caption')
          if caption:
            captions.append(caption)
          caption = slide['relationships']['image']['data']['attributes'].get('source')
          if caption:
            captions.append(caption)
          content_html += utils.add_image(img_src, ' | '.join(captions))
        content_html += slide['attributes']['content']
        content_html += '<hr/>'
  elif content_json['attributes']['format'] == 'video':
    if content_json['relationships']['video']['data']['meta'].get('jwplayer'):
      video_json = utils.get_url_json('https://cdn.jwplayer.com/v2/media/{}'.format(content_json['relationships']['video']['data']['meta']['jwplayer']['assetID']))
      if video_json:
        sources = []
        for src in video_json['playlist'][0]['sources']:
          if src['type'] == 'video/mp4':
            sources.append(src)
        video = utils.closest_dict(sources, 'height', 360)
        poster = utils.closest_dict(video_json['playlist'][0]['images'], 'width', 1000)
        content_html = utils.add_video(video['file'], 'video/mp4', poster['src'], video_json['playlist'][0]['title']) + content_html

  content_html = content_html.replace('<p>&nbsp;</p>', '')

  soup = BeautifulSoup(content_html, 'html.parser')
  for el in soup.find_all('img'):
    # Skip images we added above - attrs should only be src and width
    if len(el.attrs) == 2:
      continue
    m = re.search(r'\/image\/([0-9a-f]+)', el['src'])
    if m:
      img_src = 'https://i.insider.com/{}?width=1000&format=jpeg&auto=webp'.format(m.group(1))
    else:
      logger.warning('unknown image src {} in {}'.format(el['src'], url))
      img_src = el['src']
    captions = []
    if el.has_attr('data-mce-caption'):
      captions.append(el['data-mce-caption'])
    if el.has_attr('data-mce-source'):
      captions.append(el['data-mce-source'])
    new_el = BeautifulSoup(utils.add_image(img_src, ' | '.join(captions)), 'html.parser')
    if el.parent and el.parent.name == 'p':
      el.insert_after(new_el)
    else:
      it = el.next_element
      while it.name != 'p':
        it = it.next_element
      it.insert_before(new_el)
    el.decompose()

  for el in soup.find_all('iframe'):
    if 'youtube.com' in el['src']:
      new_el = BeautifulSoup(utils.add_youtube(el['src']), 'html.parser')
    else:
      new_el = BeautifulSoup('<p><a href="{0}">Embeded content from {0}</a></p>'.format(el['src']), 'html.parser')
    it = el.parent
    if it and it.has_attr('class') and it['class'] =='insider-raw-embed':
      it.insert_after(new_el)
      it.decompose()
    else:
      el.insert_after(new_el)
      el.decompose()

  for el in soup.find_all('blockquote'):
    if el.has_attr('class'):
      new_el = None
      if 'twitter-tweet' in el['class']:
        it = el.find_all('a')
        new_el = BeautifulSoup(utils.add_twitter(it[-1]['href']), 'html.parser')
      elif 'instagram-media' in el['class']:
        it = el.find_all('a', href=re.compile(r'instagram\.com\/\w\/([^\/]+)'))
        new_el = BeautifulSoup(utils.add_instagram(it[-1]['href']), 'html.parser')
      if new_el:
        el.insert_after(new_el)
        el.decompose()

  for el in soup.find_all('bi-shortcode'):
    if el.has_attr('id'):
      if 'related-article' in el['id']:
        it = None
        if el.has_attr('data-url'):
          it = el
        elif el.a and el.a.has_attr('data-url'):
          it = el.a
        if it:
          new_el = BeautifulSoup('<ul><li><a href="{}">{}</a></li></ul>'.format(it['data-url'], it['data-title']), 'html.parser')
          el.insert_after(new_el)
          el.decompose()
      elif el['id'] == 'commerce-link':
        # not sure how to get the link without getting and parsing the html page
        el.attrs = {}
        el.name = 'p'
      elif el['id'] == 'table-of-contents-sticky':
        el.decompose()

  for el in soup.find_all('li', id='recirc'):
    el.decompose()

  for el in soup.find_all('script'):
    el.decompose()

  for el in soup.find_all('a'):
    href = el['href']
    if el.has_attr('data-analytics-module'):
      el.attrs = {}
    # https://www.businessinsider.com/reviews/out?u=https%3A%2F%2Fwww.disneyplus.com%2Fseries%2Fthats-so-raven%2F7QEGF45PWksK
    m = re.search(r'insider\.com\/reviews\/out\?u=([^&]+)', href)
    if m:
      href = unquote_plus(m.group(1))
    el['href'] = href

  item['content_html'] = str(soup)
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)