import json, re
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging
logger = logging.getLogger(__name__)

def get_field(field):
  if field.get('data'):
    return utils.get_url_json(field['links']['related']['href'])
  return None

def get_image(field_image):
  img_src = ''
  caption = []
  image_file = None
  image_json = None

  field_json = get_field(field_image)
  if field_json:
    image_json = field_json['data']
  elif field_image.get('type'):
    image_json = field_image

  if image_json:
    if image_json['type'] == 'media--image':
      if image_json['relationships'].get('image'):
        field_json = get_field(image_json['relationships']['image'])
        image_file = field_json['data']
      if image_json['attributes'].get('field_photo_caption'):
        caption.append(image_json['attributes']['field_photo_caption']['value'])
      if image_json['attributes'].get('field_photo_credit'):
        caption.append(image_json['attributes']['field_photo_credit'])
    elif image_json['type'] == 'file--file':
      image_file = image_json

  if image_file:
    img_src = image_file['attributes']['uri']['url']
  return img_src, ' | '.join(caption)

def get_paragraphs(field_paragraph):
  paragraph_body = ''
  paragraph_json = utils.get_url_json(field_paragraph['links']['related']['href'])
  if paragraph_json:
    for paragraph in paragraph_json['data']:
      if paragraph['type'] == 'paragraph--body':
        if paragraph['attributes'].get('field_paragraph_body'):
          body = re.sub(r'^\n?<body>', '', paragraph['attributes']['field_paragraph_body']['value'])
          paragraph_body += re.sub(r'</body>$', '', body)
        else:
          logger.warning('empty paragraph--body')
      elif paragraph['type'] == 'paragraph--photographs':
        if paragraph['relationships'].get('field_photo'):
          img_src, caption = get_image(paragraph['relationships']['field_photo'])
          if img_src:
            paragraph_body += utils.add_image(img_src, caption)
          else:
            logger.warning('unhandled paragraph--photographs')
      elif paragraph['type'] == 'paragraph--embed':
        logger.debug('paragraph--embed in {}'.format(paragraph['links']['self']['href']))
        m = re.search(r'src="([^"]+)"', paragraph['attributes']['field_embed_code'])
        if m:
          paragraph_body += '<p><a href="{}">View embedded content</a></p>'.format(m.group(1))
        else:
          paragraph_body += '<p>Unhandled embedded content</p>'
      else:
        logger.warning('unhandled paragraph type {}'.format(paragraph['type']))
  return paragraph_body

def get_item(article, args, save_debug=False):
  if save_debug:
    logger.debug('getting content for ' + article['links']['self']['href'])
    utils.write_file(article, './debug/debug.json')

  split_url = urlsplit(article['links']['self']['href'])

  item = {}
  item['id'] = article['id']
  if article['attributes'].get('field_alternate_url'):
    item['url'] = article['attributes']['field_alternate_url']
  else:
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['attributes']['path']['alias'])
  item['title'] = article['attributes']['title']

  dt = datetime.fromisoformat(article['attributes']['created'])
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  # Check age
  if args.get('age'):
    if not utils.check_age(item, args):
      return None

  dt = datetime.fromisoformat(article['attributes']['changed'])
  item['date_modified'] = dt.isoformat()

  byline = ''
  field_json = get_field(article['relationships']['field_byline'])
  if field_json:
    authors = []
    for author in field_json['data']:
      authors.append(author['attributes']['title'])
    byline = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
  elif article['attributes'].get('field_byline_text'):
    byline = ', '.join(article['attributes']['field_byline_text'])
  if byline:
    item['author'] = {}
    item['author']['name'] = byline.title()

  item['tags'] = []
  field_json = get_field(article['relationships']['field_category'])
  if field_json:
    item['tags'].append(field_json['data']['attributes']['name'].title())
  field_json = get_field(article['relationships']['field_topics'])
  if field_json:
    for it in field_json['data']:
      item['tags'].append(it['attributes']['name'].title())
  if item['tags']:
    # remove dups
    item['tags'] = list(set(item['tags']))
  else:
    del item['tags']

  content_html = ''
  img_src, caption = get_image(article['relationships']['field_main_image'])
  if not img_src:
    img_src, caption = get_image(article['relationships']['field_emphasis_image'])
  if img_src:
    item['_image'] = img_src
    content_html += utils.add_image(img_src, caption)

  if article['attributes'].get('body'):
    item['summary'] = article['attributes']['body']['value']

  if article['relationships']['field_paragraphs'].get('data'):
    content_html += get_paragraphs(article['relationships']['field_paragraphs'])

  photo_gallery = get_field(article['relationships']['field_photo_gallery'])
  if photo_gallery:
    content_html += '<h3>Gallery</h3>{}'.format(photo_gallery['data']['attributes']['body']['processed'])
    gallery_images = get_field(photo_gallery['data']['relationships']['field_gallery_images'])
    if gallery_images:
      n = len(gallery_images['data'])
      for i, image in enumerate(gallery_images['data']):
        img_src, caption = get_image(image)
        if img_src:
          caption = '[{}/{}] {}'.format(i+1, n, caption)
          content_html += utils.add_image(img_src, caption)

  if content_html:
    item['content_html'] = content_html
  return item

def get_content(url, args, save_debug=False):
  item = None
  split_url = urlsplit(url)
  if save_debug:
    logger.debug('getting content from ' + url)
  article_html = utils.get_url_html(url, user_agent='desktop')
  if article_html:
    if save_debug:
      utils.write_file(article_html, './debug/debug.html')
    m = re.search(r'\\u0022guid\\u0022:\\u0022([0-9a-f\-]+)\\u0022', article_html)
    if m:
      json_url = '{}://{}/jsonapi/node/article/{}'.format(split_url.scheme, split_url.netloc, m.group(1))
      article_json = utils.get_url_json(json_url)
      if article_json:
        item = get_item(article_json['data'], args, save_debug)
  return item

def get_feed(args, save_debug=False):
  split_url = urlsplit(args['url'])
  api_url = '{}://{}/jsonapi/node/article?sort=-created'.format(split_url.scheme, split_url.netloc)
  articles_json = utils.get_url_json(api_url)
  if not articles_json:
    return None

  n = 0
  items = []
  for article in articles_json['data']:
    item = get_item(article, args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args and n == int(args['max']):
          break

  feed = utils.init_jsonfeed(args)
  feed['items'] = items.copy()
  with open('./debug/feed.json', 'w') as file:
    json.dump(feed, file, indent=4)
  return feed