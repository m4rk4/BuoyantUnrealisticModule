import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_post_content(post, args, save_debug=False):
  if save_debug:
    utils.write_file(post, './debug/debug.json')

  item = {}
  item['id'] = post['guid']['rendered']
  item['url'] = post['link']
  item['title'] = unescape(post['title']['rendered'])

  # Dates
  dt = datetime.fromisoformat(post['date_gmt']).replace(tzinfo=timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(post['modified_gmt']).replace(tzinfo=timezone.utc)
  item['date_modified'] = dt.isoformat()

  if 'age' in args:
    if not utils.check_age(item, args):
      if save_debug:
        logger.debug('skipping old post ({} {}) '.format(item['date_published'], item['_timestamp'], item['url']))
      return None

  # Authors
  author = ''
  if 'author' in post['_links']:
    for link in post['_links']['author']:
      link_json = utils.get_url_json(link['href'])
      if link_json is not None:
        if 'name' in link_json:
          if len(author) == 0:
            author = link_json['name']
          else:
            author += ', {}'.format(link_json['name'])
  if len(author) > 0:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', author)

  # Tags
  tags = []
  if 'wp:term' in post['_links']:
    for link in post['_links']['wp:term']:
      link_json = utils.get_url_json(link['href'])
      if link_json is not None:
        for entry in link_json:
          if 'name' in entry:
            tags.append(entry['name'])
  if len(tags) > 0:
    item['tags'] = tags

  # Article image
  if post.get('jetpack_featured_media_url'):
    item['_image'] = post['jetpack_featured_media_url']
  elif 'wp:featuredmedia' in post['_links']:
    for link in post['_links']['wp:featuredmedia']:
      link_json = utils.get_url_json(link['href'])
      if link_json:
        if link_json['media_type'] == 'image':
          item['_image'] = link_json['source_url']
  elif post.get('acf'):
    if post['acf'].get('hero') and post['acf']['hero'].get('image'):
      item['_image'] = post['acf']['hero']['image']
    elif post['acf'].get('post_hero') and post['acf']['post_hero'].get('image'):
      item['_image'] = post['acf']['post_hero']['image']

  # Article summary
  item['summary'] = post['excerpt']['rendered']

  content_html = ''
  if not 'nolead' in args and item.get('_image'):
    content_html += utils.add_image(item['_image'])

  if post.get('content') and post['content'].get('rendered'):
      content_html += post['content']['rendered']

  elif post.get('acf'):
    for module in post['acf']['article_modules']:
      if module['acf_fc_layout'] == 'text_block':
        content_html += module['copy']
      elif module['acf_fc_layout'] == 'list_module':
        content_html += '<h3>{}</h3>'.format(module['title'])
        if module['list_type'] == 'video':
          if 'youtube' in module['video_url']:
            for yt in re.findall(r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})', module['video_url']):
              content_html += utils.add_youtube(yt)
          else:
            logger.warning('unhandled video_url in ' + item['url'])
        else:
          logger.warning('unhandled list_type {} in {}'.format(module['list_type'], item['url']))
        content_html += module['copy']
      elif module['acf_fc_layout'] == 'image_block':
        content_html += utils.add_image(module['image'], module['caption'])
      elif module['acf_fc_layout'] == 'affiliates_block' or  module['acf_fc_layout'] == 'inline_recirculation':
        pass
      else:
        logger.warning('unhandled acf_fc_layout module {} in {}'.format(module['acf_fc_layout'], item['url']))

  else:
    logger.warning('unknown post content in {}' + item['url'])

  soup = BeautifulSoup(content_html, 'html.parser')

  for el in soup.find_all(class_='post-content-image'):
    img = el.find('img')
    if img:
      if img.get('data-lazy-srcset'):
        img_src = utils.image_from_srcset(img['data-lazy-srcset'], 1000)
      elif img.get('data-lazy-src'):
        img_src = img['data-lazy-src']
      figcaption = el.find('figcaption')
      if figcaption:
        caption = figcaption.get_text()
      else:
        caption = ''
      new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
      el.insert_after(new_el)
      el.decompose()

  for el in soup.find_all(class_='wp-caption'):
    img = el.find('img')
    if img:
      caption = ''
      img_caption = el.find(class_=re.compile(r'caption-text'))
      if img_caption:
        caption += img_caption.get_text()
      img_caption = el.find(class_=re.compile(r'image-credit'))
      if img_caption:
        if caption:
          caption += ' '
        caption += '(Credit: {})'.format(img_caption.get_text())
      new_el = BeautifulSoup(utils.add_image(img['src'], caption), 'html.parser')
      el.insert_after(new_el)
      el.decompose()

  for el in soup.find_all('img', class_=re.compile(r'wp-image-\d+')):
    if el.get('srcset'):
      img_src = utils.image_from_srcset(el['srcset'], 1000)
    else:
      img_src = el['src']
    caption = ''
    if el.parent and el.parent.name == 'p':
      el_parent = el.parent
      caption = el_parent.get_text()
    else:
      el_parent = el
    new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
    el_parent.insert_after(new_el)
    el_parent.decompose()

  for el in soup.find_all(class_='embed-youtube'):
    iframe = el.find('iframe')
    new_el = BeautifulSoup(utils.add_youtube(iframe['src']), 'html.parser')
    el.insert_after(new_el)
    el.decompose()

  for el in soup.find_all('iframe'):
    if el.get('src'):
      src = el['src']
    elif el.get('data-src'):
      src = el['data-src']
    else:
      src = ''
    if src:
      new_el = BeautifulSoup(utils.add_embed(src), 'html.parser')
      el.insert_after(new_el)
      el.decompose()
    else:
      logger.warning('unknown iframe src in ' + url)

  for el in soup.find_all(class_='blogstyle__iframe'):
    iframe = el.find('iframe')
    if iframe:
      if iframe.get('src'):
        src = iframe['src']
      elif iframe.get('data-src'):
        src = iframe['data-src']
      else:
        src = ''
      if src:
        new_el = BeautifulSoup(utils.add_embed(src), 'html.parser')
        el.insert_after(new_el)
        el.decompose()
      else:
        logger.warning('unknown iframe src in ' + url)
    else:
      it = el.find(class_='twitter-tweet')
      if it:
        links = el.find_all('a')
        new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()
      else:
        logger.warning('unhandled blogstyle__iframe in ' + item['url'])

  for el in soup.find_all(class_='twitter-tweet'):
    links = el.find_all('a')
    new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
    el.insert_after(new_el)
    el.decompose()

  for el in soup.find_all(id=re.compile(r'\bad\b')):
    el.decompose()

  for el in soup.find_all(class_=re.compile(r'\bad\b')):
    el.decompose()

  item['content_html'] = str(soup)
  return item

def get_content(url, args, save_debug=False):
  split_url = urlsplit(url)
  url_root = '{}://{}'.format(split_url.scheme, split_url.netloc)
  article_html = utils.get_url_html(url)
  if article_html:
    if save_debug:
      with open('./debug/debug.html', 'w', encoding='utf-8') as f:
        f.write(article_html)
    # Search for the direct wp-json post link
    m = re.search(r'{}\/wp-json\/wp\/v2\/posts\/\d+'.format(url_root), article_html)
    if m:
      post_url = m.group(0)
    else:
      # Search for the post id and assume the wp-json path
      m = re.search(r'{}\/\?p=(\d+)'.format(url_root), article_html)
      if m:
        post_url = '{}/wp-json/wp/v2/posts/{}'.format(url_root, m.group(1))
      else:
        logger.warning('unable to find wp-json post url in ' + url)
        return None
  post = utils.get_url_json(post_url)
  if post:
    return get_post_content(post, args, save_debug)
  return None

def get_feed(args, save_debug=False):
  if args.get('rss') or args.get('fromrss'):
    return rss.get_feed(args, save_debug, get_content)

  n = 0
  feed = utils.init_jsonfeed(args)
  posts = utils.get_url_json(args['url'])
  if posts:
    for post in posts:
      if save_debug:
        logger.debug('getting content from ' + post['link'])
      item = get_post_content(post, args, save_debug)
      if item:
        if utils.filter_item(item, args) == True:
          feed['items'].append(item)
          n += 1
          if 'max' in args:
            if n == int(args['max']):
              break
  return feed