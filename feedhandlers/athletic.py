import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

from feedhandlers import nextjs, rss
import utils

import logging
logger = logging.getLogger(__name__)

def resize_image(img_src, width=1000):
  m = re.search(r'(\/width=\d+\/)', img_src)
  if m:
    img_src = img_src.replace(m.group(1), '/width={}/'.format(width))
  elif img_src.startswith('https://cdn.theathletic.com/app/uploads/'):
    img_src = img_src.replace('https://cdn.theathletic.com/', 'https://cdn.theathletic.com/cdn-cgi/image/width={}/'.format(width))
  return img_src

def get_amp_img_src(amp_img, width=1000):
  img_src = ''
  if amp_img.get('srcset'):
    img_src = utils.image_from_srcset(amp_img['srcset'], width)
  if amp_img.get('src'):
    img_src = amp_img['src']
  return resize_image(img_src)

def get_news_content(next_data, url, args, save_debug=False):
  if not next_data:
    next_data = nextjs.get_next_data_json(url, save_debug)
    if not next_data:
      return None

  if url.endswith('/'):
    id = url.split('/')[-2]
  else:
    id = url.split('/')[-1]
  content_json = next_data['props']['apolloState']['News:'+id]

  item = {}
  item['id'] = content_json['id']
  item['url'] = content_json['permalink']
  item['title'] = content_json['headline']

  tz_est = pytz.timezone('US/Eastern')
  dt_est = datetime.fromtimestamp(content_json['published_at']/1000)
  dt = tz_est.localize(dt_est).astimezone(pytz.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt_est = datetime.fromtimestamp(content_json['last_activity_at']/1000)
  dt = tz_est.localize(dt_est).astimezone(pytz.utc)
  item['date_modified'] = dt.isoformat()

  # Check age
  if 'age' in args:
    if not utils.check_age(item, args):
      return None

  item['author'] = {}
  authors = []
  if content_json.get('byline_linkable'):
    item['author']['name'] = content_json['byline_linkable']['raw_string']
  else:
    item['author']['name'] = 'The Athletic Staff'
  if content_json.get('byline_authors'):
    for it in content_json['byline_authors']:
      author = next_data['props']['apolloState'][it['__ref']]
      if author['name'] != item['author']['name']:
        authors.append(author['name'])
  if authors:
    item['author']['name'] += ' with ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  if content_json.get('tags'):
    item['tags'] = []
    for key, val in content_json['tags'].items():
      if isinstance(val, list):
        for it in val:
          tag = next_data['props']['apolloState'][it['__ref']]
          item['tags'].append(tag['title'])
  elif content_json.get('primary_tag'):
    item['tags'] = []
    item['tags'].append(content_json['primary_tag']['title'])

  if content_json.get('images'):
    item['_image'] = content_json['images'][0]['image_uri']

  if content_json.get('custom_meta_description'):
    item['summary'] = content_json['custom_meta_description']

  item['content_html'] = ''
  if item.get('_image'):
    item['content_html'] += utils.add_image(item['_image'])
  item['content_html'] += content_json['lede']
  if content_json.get('smart_brevity'):
    item['content_html'] += '<hr/>' + content_json['smart_brevity']
  if len(content_json['images']) > 1:
    for image in content_json['images'][1:]:
      item['content_html'] += utils.add_image(image['image_uri'])
  return item

def get_content(url, args, save_debug=False):
  clean_url = utils.clean_url(url)
  if not clean_url.endswith('/'):
    clean_url += '/'
  split_url = urlsplit(clean_url)

  if split_url.path.startswith('/news/'):
    return get_news_content(None, clean_url, args, save_debug)

  amp_html = utils.get_url_html(clean_url + '?amp')
  if save_debug:
    utils.write_file(amp_html, './debug/debug.html')

  soup = BeautifulSoup(amp_html, 'html.parser')

  item = {}
  el = soup.find('script', attrs={"type": "application/ld+json"})
  if el:
    ld_json = json.loads(el.string)

    item['id'] = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, split_url.path.split('/')[1])
    item['url'] = clean_url
    item['title'] = ld_json['headline']

    # 2021-07-14 11:00:01
    dt = datetime.strptime(ld_json['datePublished'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = datetime.strptime(ld_json['dateModified'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for author in ld_json['author']:
      authors.append(author['name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if ld_json.get('keywords'):
      item['tags'] = ld_json['keywords'].copy()

    item['_image'] = ld_json['thumbnailUrl']
    item['summary'] = ld_json['description']
  else:
    logger.warning('unable to get content details for ld+json in ' + clean_url)

  article = soup.find('section', attrs={"subscriptions-section": "content"})
  for el in article.find_all('div', id=re.compile(r'attachment_\d+')):
    it = article.find('div', class_='wp-caption-image-container')
    if it:
      it = el.find('amp-img')
      img_src = get_amp_img_src(it)
      caption = ''
      it = el.find('div', class_='inline-credits')
      if it:
        caption = it.get_text()
      new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
      el.insert_after(new_el)
      el.decompose()
    else:
      logger.warning('unhandled attachment in ' + clean_url)

  for el in article.find_all('amp-img'):
    img_src = get_amp_img_src(el)
    new_el = BeautifulSoup(utils.add_image(img_src), 'html.parser')
    el.insert_after(new_el)
    el.decompose()

  for el in article.find_all('div', class_='wp-video'):
    it = el.find('amp-video')
    if it:
      new_el = BeautifulSoup(utils.add_video(it.source['src'], it.source['type'], it['poster']), 'html.parser')
      el.insert_after(new_el)
      el.decompose()
    else:
      logger.warning('unhandled video in ' + clean_url)

  for el in article.find_all('div', id=re.compile(r'ath_table_\d+')):
    table = el.find('table')
    if table:
      if table.get('class'):
        del table['class']
      table['style'] = 'margin-left:auto; margin-right:auto;'
      for it in table.find_all(['td', 'th']):
        if it.get('class'):
          del it['class']
        it['style'] = 'text-align:center; padding-left:1em; padding-right:1em;'
      el.insert_after(table)
      it = el.find('div', id='table_title')
      if it:
        new_el = BeautifulSoup('<center><b>{}</b></center>'.format(it.get_text()), 'html.parser')
        el.insert_after(new_el)
      el.decompose()
    else:
      logger.warning('unhandled table in ' + clean_url)

  item['content_html'] = ''

  # find lead image
  el = soup.find('div', class_='article-main-image')
  if el:
    it = el.find('amp-img')
    if it:
      img_src = get_amp_img_src(it)
      item['content_html'] += utils.add_image(img_src)
  else:
    el = soup.find('div', class_=re.compile('-hero'))
    if el:
      it = el.parent
      m = re.search(r'url\((.*)\)', it['style'])
      if m:
        img_src = resize_image(m.group(1))
        item['content_html'] += utils.add_image(img_src)

  item['content_html'] += str(article)
  return item

def get_news_feed(args, save_debug=False):
  next_data = nextjs.get_next_data_json(args['url'], save_debug)
  if not next_data:
    return None
  n = 0
  items = []
  for key, val in next_data['props']['apolloState'].items():
    if key.startswith('News:'):
      if save_debug:
        logger.debug('getting content from ' + val['permalink'])
      item = get_news_content(next_data, val['permalink'], args, save_debug)
      if item:
        if utils.filter_item(item, args) == True:
          items.append(item)
          n += 1
          if 'max' in args:
            if n == int(args['max']):
              break
  feed = utils.init_jsonfeed(args)
  feed['items'] = items.copy()
  return feed

def get_feed(args, save_debug=False):
  if 'rss' in args['url']:
    return rss.get_feed(args, save_debug, get_content)
  else:
    return get_news_feed(args, save_debug)