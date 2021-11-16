import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def resize_image(img_src, width=1000):
  return '{}?w={}'.format(utils.clean_url(img_src), width)

def get_content(url, args, save_debug=False):
  clean_url = utils.clean_url(url)
  m = re.search(r'-(\d+)\/?$', clean_url)
  if not m:
    logger.warning('unable to parse post id from ' + url)
    return None

  api_url = 'https://www.rollingstone.com/wp-json/mobile-apps/v1/article/' + m.group(1)
  post_json = utils.get_url_json(api_url)
  if not post_json:
    return None
  if save_debug:
    utils.write_file(post_json, './debug/debug.json')

  item = {}
  item['id'] = post_json['post-id']
  item['url'] = post_json['permalink']
  item['title'] = post_json['headline']

  tz_est = pytz.timezone('US/Eastern')
  dt_loc = datetime.fromisoformat(post_json['published-at'])
  dt_utc = tz_est.localize(dt_loc).astimezone(pytz.utc)
  item['date_published'] = dt_utc.isoformat()
  item['_timestamp'] = dt_utc.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt_utc.strftime('%b'), dt_utc.day, dt_utc.year)

  dt_loc = datetime.fromisoformat(post_json['updated-at'])
  dt_utc = tz_est.localize(dt_loc).astimezone(pytz.utc)
  item['date_modified'] = dt_utc.isoformat()

  item['author'] = {}
  item['author']['name'] = post_json['byline']

  item['tags'] = []
  for tag in post_json['tags']:
    item['tags'].append(tag['name'])

  item['summary'] = post_json['body-preview']

  lede = ''
  if post_json.get('featured-video'):
    lede += utils.add_embed(post_json['featured-video'])

  if post_json.get('featured-image'):
    for img in post_json['featured-image']['crops']:
      if img['name'] == 'full':
        item['_image'] = img['url']
        if not lede:
          caption = []
          if img.get('caption'):
            caption.append(img['caption'])
          if img.get('credit'):
            caption.append(img['credit'])
          lede += utils.add_image(resize_image(img['url']), ' | '.join(caption))
        break

  if post_json.get('tagline'):
    lede = '<p><i>{}</i></p>'.format(post_json['tagline']) + lede

  if post_json.get('review_meta') and post_json['review_meta'].get('rating'):
    lede += '<h3>{}<br/>{}<br/><span style="font-size:1.5em;">{} / {}</span></h3>'.format(post_json['review_meta']['title'], post_json['review_meta']['artist'], post_json['review_meta']['rating'], post_json['review_meta']['rating_out_of'])

  soup = BeautifulSoup(post_json['body'], 'html.parser')

  for el in soup.find_all(id=re.compile(r'attachment_\d+')):
    if el.img:
      if 'alignleft' in el['class']:
        el.img['style'] = 'float:left; margin-right:8px;'
        el.parent.insert_after(BeautifulSoup('<div style="clear:left;"></div>', 'html.parser'))
      else:
        caption = []
        it = el.find(class_='wp-caption-text')
        if it:
          caption.append(it.get_text())
        it = el.find(class_='rs-image-credit')
        if it:
          caption.append(it.get_text())
        new_html = utils.add_image(resize_image(el.img['src']), ' | '.join(caption))
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

  for el in soup.find_all('iframe'):
    new_html = utils.add_embed(el['src'])
    if el.parent.name == 'b':
      el.parent.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.parent.decompose()
    else:
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  item['content_html'] = lede + str(soup)
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)