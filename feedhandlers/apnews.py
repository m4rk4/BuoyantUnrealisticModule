import json, os, re
from datetime import datetime, timezone

import utils

import logging
logger = logging.getLogger(__name__)

def add_media(media):
  def_img_size = 800
  if media['type'] == 'Photo':
    sizes = media['imageRenderedSizes'] 
    size = sizes[min(range(len(sizes)), key = lambda i: abs(sizes[i] - def_img_size))]
    url = media['gcsBaseUrl'] + str(size) + media['imageFileExtension']
    media_html = utils.add_image(url, media['flattenedCaption'])
  elif media['type'] == 'YouTube':
    media_html = utils.add_youtube(media['externalId'], media['flattenedCaption'])
  else:
    logger.warning('Unhandled media type {}' + media['type'])
  return media_html 

def get_image_url(img_id, file_ext='.jpeg', img_width=600):
  return 'https://storage.googleapis.com/afs-prod/media/{}/{}{}'.format(img_id, img_width, file_ext)

def get_item(content_data, args):
  item = {}
  item['id'] = content_data['id']
  item['url'] = content_data['localLinkUrl']
  item['title'] = content_data['headline']

  # Dates
  dt_pub = None
  if content_data.get('published'):
    dt_pub = datetime.fromisoformat(content_data['published']).replace(tzinfo=timezone.utc)
  dt_mod = None
  if content_data.get('updated'):
    dt_mod = datetime.fromisoformat(content_data['updated']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt_mod.isoformat()
  if not dt_pub and dt_mod:
    dt_pub = dt_mod
  if dt_pub:
    item['date_published'] = dt_pub.isoformat()
    item['_timestamp'] = dt_pub.timestamp()
    item['_display_date'] = dt_pub.strftime('%b %-d, %Y')

  if not utils.check_age(item, args):
    return None

  # Authors
  if content_data.get('bylines'):
    item['author'] = {}
    m = re.search(r'^By\s(.*)', content_data['bylines'], flags=re.I)
    if m:
      item['author']['name'] = m.group(1).title().replace('And', 'and')
    else:
      item['author']['name'] = content_data['bylines'].title().replace('And', 'and')

  # Tags
  if content_data.get('tagObjs'):
    item['tags'] = []
    for tag in content_data['tagObjs']:
      item['tags'].append(tag['name'])

  # Article image
  if content_data.get('leadPhotoId'):
    item['image'] = get_image_url(content_data['leadPhotoId'])

  # Article summary
  item['summary'] = content_data['flattenedFirstWords']

  # Article html
  def sub_divs(matchobj):
    nonlocal args
    nonlocal content_data

    m = re.search(r'class=["\']([^"\']+)["\']', matchobj.group(1))
    if m:
      if m.group(1) == 'ad-placeholder':
        return ''
      
      m_id = re.search(r'id=["\']([^"\']+)["\']', matchobj.group(1))
      if not m_id:
        logger.warning('can not parse id for placeholder {} in {}'.format(matchobj.group(1), args['url']))
        return ''

      if m.group(1) == 'media-placeholder':
        if content_data.get('media'):
          for it in content_data['media']:
            if it['id'] == m_id.group(1):
              return add_media(it)
        else:
          return utils.add_image(get_image_url(it['id']))

      elif m.group(1) == 'related-story-embed':
        for it in content_data['relatedStoryEmbeds']:
          if it['id'] == m_id.group(1):
            html = '<h4>{}</h4><ul>'.format(it['introText'])
            for li in it['contentsList']:
              li_data = utils.get_url_json('https://storage.googleapis.com/afs-prod/contents/' + li['contentId'])
              if li_data:
                title = li_data['headline']
                desc = li_data['flattenedFirstWords']
              else:
                title, desc = utils.get_url_title_desc(li['url'])
              html += '<li><a href="{}">{}</a><br />{}</li>'.format(li['url'], title, desc)
            html += '</ul>'
            return html
  
      elif m.group(1) == 'hub-link-embed':
        for it in content_data['richEmbeds']:
          if it['id'] == m_id.group(1):
            #print(it['calloutText'])
            return '<h4>{} &ndash; <a href="https://apnews.com/hub/{}">{}</a></h4>'.format(it['calloutText'], it['tag']['id'], it['displayName'])
      else:
        logger.warning('unhandled placeholder {} in {}'.format(m.group(1), args['url']))

    else:
      logger.warning('unhandled placeholder {} in {}'.format(matchobj.group(0), args['url']))
    return ''

  #content_html = re.sub(r'<div([^>]+)>([^<]*)</div>', sub_divs, content_data['storyHTML'])

  item['content_html'] = ''
  if content_data.get('leadPhotoId'):
    if content_data.get('media'):
      for it in content_data['media']:
        if it['id'] == content_data['leadPhotoId']:
          item['content_html'] = add_media(it)
          break
    else:
      item['content_html'] = utils.add_image(item['image'])
    # Remove because Inoreader uses the image as a lead
    del item['image']

  item['content_html'] += re.sub(r'<div([^>]+)>([^<]*)</div>', sub_divs, content_data['storyHTML'])

  if content_data.get('media'):
    for it in content_data['media']:
      exists = False
      if re.search(it['id'], item['content_html']):
        exists = True
      elif it.get('externalId'):
        if re.search(it['externalId'], item['content_html']):
          exists = True
      if not exists:
        item['content_html'] += add_media(it)

  return item

def get_content(url, args, save_debug=False):
  html = utils.get_url_html(url)
  if not html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(html)

  m = re.search(r"window\[\'titanium-state\'\]\s=\s(.*)\swindow\[\'titanium-cacheConfig\'\]", html, flags=re.S)
  if not m:
    logger.warning('Unable to find article json data in ' + url)
    return None
  if save_debug:
    with open('./debug/debug.txt', 'w', encoding='utf-8') as f:
      f.write(m.group(1))

  try:
    article_json = json.loads(m.group(1))
  except:
    logger.warning('Error loading content json in ' + url)
    return None
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(article_json, file, indent=4)

  for key, data in article_json['content']['data'].items():
    return get_item(data, args)

def get_feed(args_orig, save_debug=False):
  args = args_orig.copy()
  if args.get('tags'):
    args['url'] = 'https://afs-prod.appspot.com/api/v2/feed/tag?tags=' + args['tags']
    if not args.get('title'):
      args['title'] = 'AP News > ' + args['tags']
    if not args.get('home_page_url'):
      args['home_page_url'] = 'https://apnews.com/' + args['tags']

  feed = utils.init_jsonfeed(args)

  posts = utils.get_url_json(args['url'])
  if posts is None:
    return feed
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(posts, file, indent=4)

  # Loop through each post
  n = 0
  for card in posts['cards']:
    for content in card['contents']:
      if content.get('gcsUrl'):
        content_data = utils.get_url_json(content['gcsUrl'])
      else:
        content_data = utils.get_url_json('https://storage.googleapis.com/afs-prod/contents/' + content['id'])
      if content_data:
        item = get_item(content_data, args)
      else:
        item = get_item(content, args)
      if item:
        if utils.filter_item(item, args) == True:
          feed['items'].append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            return feed

    for card_feed in card['feed']:
      for content in card_feed['contents']:
        if content.get('gcsUrl'):
          content_data = utils.get_url_json(content['gcsUrl'])
        else:
          content_data = utils.get_url_json('https://storage.googleapis.com/afs-prod/contents/' + content['id'])
        if content_data:
          item = get_item(content_data, args)
        else:
          item = get_item(content, args)
        if item:
          if utils.filter_item(item, args) == True:
            feed['items'].append(item)
            n += 1
            if 'max' in args:
              if n == int(args['max']):
                return feed
  return feed