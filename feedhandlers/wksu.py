import html, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def get_audio(el_audio):
  audio_src = ''
  audio_type = ''
  audio_name = ''
  el = el_audio.find('ps-stream-url')
  if el:
    audio_src = el['data-stream-url']
    audio_type = el.get('data-stream-format')
    if not audio_type and 'mp3' in el['data-stream-url']:
      audio_type = 'audio/mpeg'
  el = el_audio.find('ps-stream')
  if el:
    if el.get('data-stream-name'):
      audio_name = el['data-stream-name']
  return audio_src, audio_type, audio_name

def get_image(el_image):
  img = el_image.find('img')
  images = []
  if img.has_attr('srcset'):
    for it in img['srcset'].split(','):
      img_src = it.split(' ')[0]
      m = re.search(r'\/resize\/(\d+)x(\d+)', img_src)
      if m:
        image = {}
        image['src'] = img_src
        image['width'] = int(m.group(1))
        image['height'] = int(m.group(2))
        images.append(image)
  if img.has_attr('data-src'):
    img_src = img['data-src']
    m = re.search(r'\/resize\/(\d+)x(\d+)', img_src)
    if m:
      image = {}
      image['src'] = img_src
      image['width'] = int(m.group(1))
      image['height'] = int(m.group(2))
      images.append(image)
  if img.has_attr('loading'):
    img_src = img['src']
    if img['loading'] != 'lazy':
      m = re.search(r'\/resize\/(\d+)x(\d+)', img_src)
      if m:
        image = {}
        image['src'] = img_src
        image['width'] = int(m.group(1))
        image['height'] = int(m.group(2))
        images.append(image)
  if images:
    qs = parse_qs(urlsplit(images[0]['src']).query)
    if qs and qs.get('url'):
      m = re.search(r'\/crop\/(\d+)x(\d+)', images[0]['src'])
      if m:
        image = {}
        image['src'] = qs['url'][0]
        image['width'] = int(m.group(1))
        image['height'] = int(m.group(2))
        images.append(image)
    img = utils.closest_dict(images, 'width', 1000)
    img_src = img['src']

  caption = []
  it = el_image.find(class_='Figure-caption')
  if it:
    text = it.get_text().strip()
    if text:
      caption.append(text)
  it = el_image.find(class_='Figure-credit')
  if it:
    text = it.get_text().strip()
    if text:
      caption.append(text)
  it = el_image.find(class_='Figure-source')
  if it:
    text = it.get_text().strip()
    if text:
      caption.append(text)
  return img_src, ' | '.join(caption)

def get_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None

  soup = BeautifulSoup(article_html, 'html.parser')
  el = soup.find('meta', attrs={"name": "brightspot-dataLayer"})
  if not el:
    logger.warning('unable to find brightspot-dataLayer')
    return None

  data_json = json.loads(html.unescape(el['content']))
  if save_debug:
    utils.write_file(data_json, './debug/debug.json')

  item = {}
  item['id'] = data_json['nprStoryId']
  item['url'] = url
  item['title'] = data_json['storyTitle']

  # This seems to correspond to the rss feed date
  el = soup.find('meta', attrs={"property": "article:published_time"})
  if el:
    date = re.sub(r'\.\d\d$', '', el['content']) + '+00:00'
    dt = datetime.fromisoformat(date)
  else:
    dt = datetime.fromisoformat(data_json['publishedDate'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  el = soup.find('meta', attrs={"property": "article:modified_time"})
  if el:
    date = re.sub(r'\.\d\d$', '', el['content']) + '+00:00'
    dt = datetime.fromisoformat(date)
    item['date_modified'] = dt.isoformat()

  item['author'] = {}
  item['author']['name'] = data_json['author']

  item['tags'] = data_json['keywords'].split(',')

  el = soup.find('meta', attrs={"property": "og:image"})
  if el:
    item['_image'] = el['content']

  el = soup.find('meta', attrs={"property": "og:description"})
  if el:
    item['summary'] = el['content']

  item['content_html'] = ''
  el = soup.find(class_='ArticlePage-lead')
  if el:
    img_src, caption = get_image(el)
    item['content_html'] += utils.add_image(img_src, caption)
  elif item.get('_image'):
    item['content_html'] += utils.add_image(item['image'])

  el = soup.find(class_='ArticlePage-audioPlayer')
  if el:
    audio_src, audio_type, audio_name = get_audio(el)
    if audio_src:
      attachment = {}
      attachment['url'] = audio_src
      attachment['mime_type'] = audio_type
      item['attachments'] = []
      item['attachments'].append(attachment)
      item['_audio'] = audio_src
      item['content_html'] += '<blockquote><h4><a style="text-decoration:none;" href="{0}">&#9654;</a>&nbsp;<a href="{0}">Listen</a></h4></blockquote>'.format(audio_src)

  article = soup.find(class_='ArticlePage-articleBody')

  for el in article.find_all(class_='Enhancement'):
    new_html = ''
    if el.find(class_='Quote'):
      it = el.find(class_='Quote-attribution')
      if it:
        author = it.get_text()
      else:
        author = ''
      new_html = utils.add_pullquote(el.blockquote.get_text(), author)

    elif el.find(class_='AudioEnhancement'):
      audio_src, audio_type, audio_name = get_audio(el)
      desc = ''
      it = el.find(class_='AudioEnhancement-description')
      if it:
        desc += ' &ndash; {}'.format(el.get_text().strip())
      if not desc and audio_name:
        desc += ' &ndash; {}'.format(audio_name)
      new_html = '<blockquote><h4><a style="text-decoration:none;" href="{0}">&#9658;</a>&nbsp;<a href="{0}">Listen</a>{1}</h4></blockquote>'.format(audio_src, desc)

    elif el.find(class_='Figure'):
      img_src, caption = get_image(el)
      new_html = utils.add_image(img_src, caption)

    elif el.find(class_='twitter-tweet'):
      tweet_url = el.find_all('a')
      m = re.search(r'(https:\/\/twitter\.com/[^\/]+\/status\/\d+)', tweet_url[-1]['href'])
      if m:
        new_html = utils.add_twitter(m.group(1))

    elif el.find('ps-youtubeplayer'):
      caption = ''
      it = el.find(class_='VideoEnhancement-title')
      if it:
        caption = it.get_text()
      new_html = utils.add_video(el.iframe['src'], 'youtube')

    else:
      logger.warning('unhandled Enhancement in ' + url)

    if new_html:
      new_el = BeautifulSoup(new_html, 'html.parser')
      el.insert_after(new_el)
      el.decompose()

  for el in article.find_all(class_='fullattribution'):
    it = el.find('img')
    if it and it.has_attr('src') and 'google-analytics' in it['src']:
      it.decompose()

  item['content_html'] += str(article)
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)