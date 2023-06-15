import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def resize_image(image, width=1000):
  if image.get('cdn'):
    sizes = []
    for size in image['cdn']['sizes']:
      if not re.search(r'cTC|cMC', size, flags=re.I):
        m = re.search(r'^(\d+)x', size)
        if m:
          s = {"width": int(m.group(1)), "size": size}
          sizes.append(s)
    size = utils.closest_dict(sizes, 'width', width)
    img_src = 'https://{}/{}/{}'.format(image['cdn']['host'], size['size'], image['cdn']['fileName'])
  else:
    size = image['url'].split('/')[-2]
    img_src = image['url'].replace(size, '{}x'.format(width))
  return img_src

def add_image(image):
  captions = []
  if image.get('caption'):
    captions.append(image['caption'])
  if image.get('photoCredit'):
    captions.append(image['photoCredit'])
  return utils.add_image(resize_image(image), ' | '.join(captions))

def get_content(url, args, site_json, save_debug=False):
  split_url = urlsplit(url)
  m = re.search(r'\/(\d+)$', split_url.path)
  if not m:
    logger.warning('unable to parse article id in ' + url)
    return None

  article_json = utils.get_url_json('https://api2.post-gazette.com/top/2/article/{}/'.format(m.group(1)))
  if not article_json:
    return None
  if save_debug:
    utils.write_file(article_json, './debug/debug.json')

  article = article_json['articles'][0]
  item = {}
  item['id'] = article['storyID']
  item['url'] = article['link']
  item['title'] = article['title']

  dt = datetime.strptime(article['pubDate'], '%a, %d %b %Y %H:%M:%S %z').astimezone(timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = utils.format_display_date(dt)
  dt = datetime.strptime(article['contentModified'], '%a, %d %b %Y %H:%M:%S %z').astimezone(timezone.utc)
  item['date_modified'] = dt.isoformat()

  item['author'] = {}
  item['author']['name'] = re.sub(r'^By ', '', article['author'])

  item['_image'] = resize_image(article['images'][0])

  article_images = article['images'].copy()

  item['content_html'] = add_image(article_images[0])
  del article_images[0]

  soup = BeautifulSoup(article['body'], 'html.parser')

  for el in soup.find_all(class_='pg-embedcode-largeimage'):
    new_html = ''
    title = el.img['src'].split('/')[-1].lower()
    for i, image in enumerate(article_images):
      if title in image['url']:
        new_html = add_image(image)
        del article_images[i]
        break
    if not new_html:
      captions = []
      it = el.find(class_='pg-embedcode-largeimage-text')
      if it:
        caption = it.get_text().strip()
        if caption:
          captions.append(caption)
      it = el.find(class_='pg-embedcode-largeimage-credit')
      if it:
        caption = it.get_text().strip()
        if caption:
          captions.append(caption)
      new_html = utils.add_image(el.img['src'], ' | '.join(captions))
    new_el = BeautifulSoup(new_html, 'html.parser')
    el.insert_after(new_el)
    el.decompose()

  for el in soup.find_all('blockquote', class_='twitter-tweet'):
    tweet_url = el.find_all('a')
    m = re.search(r'https:\/\/twitter\.com/[^\/]+\/status\/\d+', tweet_url[-1]['href'])
    if m:
      new_html = utils.add_embed(m.group(0))
      new_el = BeautifulSoup(new_html, 'html.parser')
      el.insert_after(new_el)
      el.decompose()

  for el in soup.find_all(attrs={"data-ps-embed-type": "slideshow"}):
    slideshow_html = utils.get_url_html('https://post-gazette.photoshelter.com/embed?type=slideshow&G_ID=' + el['data-ps-embed-gid'])
    m = re.search(r'"api_key":"(\w+)"', slideshow_html)
    if m:
      post_data = {"fields": "*", "f_https_link": "t", "api_key": m.group(1)}
      slideshow_json = utils.post_url('https://post-gazette.photoshelter.com/psapi/v2.0/gallery/' + el['data-ps-embed-gid'], data=post_data)
      if slideshow_json:
        post_data = {"fields": "*", "f_https_link": "t", "page": 1, "ppg": 250, "limit": 250, "offset": 0, "api_key": m.group(1)}
        images_json = utils.post_url('https://post-gazette.photoshelter.com/psapi/v2.0/gallery/{}/images'.format(el['data-ps-embed-gid']), data=post_data)
        if images_json:
          new_html = '<h3>Gallery: {} ({} images)</h3>'.format(slideshow_json['data']['name'], len(images_json['data']['images']))
          for image in images_json['data']['images']:
            img_src = '{}/sec={}/fit=1000x800'.format(image['link_elements']['base'], image['link_elements']['token'])
            caption = image['caption'].replace('#standalone', '').strip()
            new_html += utils.add_image(img_src, caption) + '<br/>'
          new_el = BeautifulSoup(new_html, 'html.parser')
          el.insert_after(new_el)
          el.decompose()

  for el in soup.find_all('iframe'):
    new_html = utils.add_embed(el['src'])
    new_el = BeautifulSoup(new_html, 'html.parser')
    el_parent = el
    if el.parent and (el.parent.name == 'p' or el.parent.name == 'div'):
      el_parent = el.parent
    el_parent.insert_after(new_el)
    el_parent.decompose()

  for el in soup.find_all('script'):
    el.decompose()

  item['content_html'] += str(soup)

  if article_images:
    for image in article_images:
      item['content_html'] += add_image(image) + '<br/>'

  return item

def get_feed(url, args, site_json, save_debug=False):
  return rss.get_feed(url, args, site_json, save_debug, get_content)