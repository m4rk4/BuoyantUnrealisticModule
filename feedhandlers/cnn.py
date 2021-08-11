import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from html import unescape
from urllib.parse import urlsplit

from feedhandlers import rss, twitter
import utils

import logging
logger = logging.getLogger(__name__)

def get_resized_image(images, width_target=640):
  widths = []
  # Check the resized images
  for key, val in images.items():
    widths.append(val['width'])
  w = widths[min(range(len(widths)), key=lambda i: abs(widths[i]-width_target))]
  for key, val in images.items():
    if val['width'] == w:
      image = images[key]
      # Prefix with https if missing
      if not re.search(r'^http', image['uri']):
        image['uri'] = 'https:' + image['uri']
      return image
  return None

def get_video_info_json(video_id, save_debug):
  info_url = 'https://fave.api.cnn.io/v1/video?id={}&customer=cnn&edition=domestic&env=prod'.format(video_id)
  info_json = utils.get_url_json(info_url)
  if info_json:
    if save_debug:
      with open('./debug/video.json', 'w') as file:
        json.dump(info_json, file, indent=4)
  else:
    logger.warning('unable to get video info from ' + info_url)
  return info_json

def process_element(element, url, save_debug=False):
  element_html = ''
  element_contents = None
  if element.get('elementContents'):
    element_contents = element['elementContents']
    if isinstance(element['elementContents'], dict):
      if element['elementContents'].get('type'):
        element_contents = element['elementContents'][element['elementContents']['type']]    

  if re.search('article|featured-video-collection|myfinance|read-more', element['contentType']):
    pass

  elif element['contentType'] == 'sourced-paragraph':
    element_html += '<p>'
    if element_contents.get('location') or element_contents.get('source'):
      element_html += '<b>'
    if element_contents.get('location'):
      element_html += element_contents['location']
    if element_contents.get('source'):
      if element_contents.get('location'):
        element_html += '&nbsp;'
      element_html += '({})'.format(element_contents['source'])
    if element_contents.get('location') or element_contents.get('source'):
        element_html += '&nbsp;&ndash;&nbsp;</b>&nbsp;'
    for text in element_contents['formattedText']:
      element_html += text
    element_html += '</p>'

  elif element['contentType'] == 'editorial-note':
    element_html += '<p><small><i><b>Editor\'s note:</b> '
    for text in element_contents:
      element_html += text
    element_html += '</i></small></p>'

  elif element['contentType'] == 'factbox':
    if not re.search(r'get our free|sign up', element_contents['title'], flags=re.I):
      element_html += '<blockquote><b>{}</b><br>'.format(element_contents['title'])
      for text in element_contents['text']:
        element_html += text['html'][0]
      element_html += '</blockquote>'

  elif element['contentType'] == 'pullquote':
    element_html += '<blockquote><b>{}</b><br> &ndash; {}</blockquote>'.format(element_contents['quote'], element_contents['author'])

  elif element['contentType'] == 'raw-html':
    if not re.search(r'\bjs-cnn-erm\b|Click to subscribe|float:left;|float:right;', element_contents['html'], flags=re.I):
      element_html += re.sub(r'(\/\/[^\.]*.cnn\.com)', r'https:\1', element_contents['html'])

  elif element['contentType'] == 'image':
    image = get_resized_image(element_contents['cuts'])
    caption = element_contents['caption']
    if element_contents.get('photographer'):
      caption += ' ({})'.format(element_contents['photographer'])
    elif element_contents.get('source'):
      caption += ' ({})'.format(element_contents['source'])
    element_html += utils.add_image(image['uri'], caption)

  elif element['contentType'] == 'gallery-full':
    n = 1
    if element.get('gallerycount'):
      gallery_count = element['gallerycount']
    else:
      gallery_count = len(element_contents)
    for content in element_contents:
      if content['contentType'] == 'image':
        image = get_resized_image(content['elementContents']['cuts'])
        caption = '[{}/{}] '.format(n, gallery_count)
        caption += content['elementContents']['caption'][0]
        if content['elementContents'].get('photographer'):
          caption += ' ({})'.format(content['elementContents']['photographer'])
        elif content['elementContents'].get('source'):
          caption += ' ({})'.format(content['elementContents']['source'])
        caption = caption.replace('"', '&quot;')          
        element_html += utils.add_image(image['uri'], caption)
        n += 1

  elif element['contentType'] == 'video-demand':
    video_info = get_video_info_json(element_contents['videoId'], save_debug)
    if video_info:
      video_src = ''
      for vid in video_info['files']:
        if 'mp4' in vid['bitrate']:
          video_src = vid['fileUri']
          video_type = 'video/mp4'
          break
      if video_src:
        caption = ''
        if video_info.get('headline'):
          caption += video_info['headline'].strip()
        if video_info.get('description'):
          if caption and not caption.endswith('.'):
            caption += '. '
          caption += video_info['description'].strip()

        for img in reversed(video_info['images']):
          poster = img['uri']
          if img['name'] == '640x360':
            break
        element_html += utils.add_video(video_src, video_type, poster, caption)

  elif element['contentType'] == 'animation':
    video_src = re.sub(r'w_\d+', 'w_640', element['elementContents']['cuts']['medium']['uri'])
    element_html += utils.add_video(video_src, 'video/mp4', video_src.replace('.mp4', '.jpg'))

  elif element['contentType'] == 'youtube':
    if element_contents.get('embedUrl'):
      element_html += utils.add_youtube(element_contents['embedUrl'])
    elif element_contents.get('embedHtml'):
      element_html += utils.add_youtube(element_contents['embedHtml'])
    else:
      logger.warning('trouble embedding YouTube video in ' + url)

  elif element['contentType'] == 'instagram':
    logger.warning('CNN instagram embed in ' + url)
    #element_html += element_contents['embedHtml']
    element_html += utils.add_instagram(element_contents['embedHtml'])

  elif element['contentType'] == 'twitter':
    #logger.warning('CNN twitter embed in ' + url)
    #element_html += element_contents['embedHtml']
    tweet = twitter.get_content(element_contents['embedUrl'], None, save_debug)
    if tweet:
      element_html += tweet['content_html']
    else:
      m = re.search(r'^(<blockquote.*<\/blockquote>)', element_contents['embedHtml'])
      if m:
        element_html += m.group(1)
      else:
        logger.warning('unable to add tweet {} in {}'.format(element_contents['embedUrl'], url))

  else:
    logger.warning('unhandled element type {} in {}'.format(element['contentType'], url))
  return element_html

def get_item_info(article_json, save_debug=False):
  item = {}
  item['id'] = article_json['sourceId']
  item['url'] = article_json['canonicalUrl']
  item['title'] = article_json['title']

  dt = datetime.fromisoformat(article_json['firstPublishDate'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(article_json['lastPublishDate'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  author = ''
  if isinstance(article_json['bylineProfiles'], list):
    byline_profiles = article_json['bylineProfiles']
  else:
    byline_profiles = article_json['bylineProfiles'][article_json['bylineProfiles']['type']]
  if len(byline_profiles) > 0:
    authors = []
    for byline in byline_profiles:
      authors.append(byline['name'])
    item['author'] = {}
    if authors:
      item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
      item['author']['name'] = 'CNN'
  else:
    item['author'] = {}
    item['author']['name'] = re.sub(r', CNN.*$', '', article_json['bylineText'])

  if article_json.get('metaKeywords'):
    tags = article_json['metaKeywords'].replace(article_json['title'] + ' - CNN', '').strip()
    if tags.endswith(','):
      tags = tags[:-1]
    item['tags'] = [tag.strip() for tag in tags.split(',')]

  item['image'] = 'https:' + article_json['metaImage']
  item['summary'] = article_json['description']
  return item

def get_content_from_html(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(article_html)

  item = {}
  item['id'] = url
  item['url'] = url

  soup = BeautifulSoup(article_html, 'html.parser')
  for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
    info = json.loads(el.string)
    if save_debug:
      with open('./debug/debug.json', 'w') as file:
        json.dump(info, file, indent=4)

    if info.get('headline'):
      item['title'] = unescape(info['headline'])
    elif info.get('title'):
      item['title'] = unescape(info['title'])
    elif info.get('name'):
      item['title'] = unescape(info['name'])

    dt_pub = None
    if info.get('datePublished'):
      dt_pub = datetime.fromisoformat(info['datePublished'].replace('Z', '+00:00'))
    elif info.get('uploadDate'):
      dt_pub = datetime.fromisoformat(info['uploadDate'].replace('Z', '+00:00'))
    if dt_pub:
      item['date_published'] = dt_pub.isoformat()
      item['_timestamp'] = dt_pub.timestamp()
      item['_display_date'] = dt_pub.strftime('%b %-d, %Y')

    if info.get('dateModified'):
      dt_mod = datetime.fromisoformat(info['dateModified'].replace('Z', '+00:00'))
      item['date_modified'] = dt_mod.isoformat()

    item['author'] = {}
    if info.get('author'):
      item['author']['name'] = re.sub(r', CNN.*$', '', info['author']['name'])
    else:
      item['author']['name'] = 'CNN'
    
    if info.get('image'):
      if isinstance(info['image'], dict):
        item['_image'] = info['image']['url']
      else:
        item['_image'] = info['image']

    if info.get('description'):
      item['summary'] = unescape(info['description'])

    if info.get('@type') == 'VideoObject':
      item['content_html'] = unescape(info['description'])
      m = re.search(r'\"videoId\":"([^\"]+)\"', article_html)
      if m:
        video_info = get_video_info_json(m.group(1), save_debug)
        if video_info:
          video_src = ''
          for vid in video_info['files']:
            if 'mp4' in vid['bitrate']:
              video_src = vid['fileUri']
              video_type = 'video/mp4'
              break
          if video_src:
            if video_src.startswith('/'):
              video_src = 'https://ht.cdn.turner.com/cnn/big' + video_src
            caption = ''
            if video_info.get('headline'):
              caption += video_info['headline'].strip()
            if video_info.get('description'):
              if caption and not caption.endswith('.'):
                caption += '. '
              caption += video_info['description'].strip()
            for img in reversed(video_info['images']):
              poster = img['uri']
              if img['name'] == '640x360':
                break
            item['content_html'] = utils.add_video(video_src, video_type, poster)
            item['content_html'] += '<p>{}</p>'.format(caption)
            return item

  # Fallbacks
  if not item.get('title'):
    it = soup.find('meta', attrs={"property": "og:title"})
    if it:
      item['title'] = unescape(it['content'])

  if not item.get('date_published'):
    it = soup.find('meta', attrs={"name": "article:published_time"})
    if it:
      dt_pub = datetime.fromisoformat(it['content'].replace('Z', '+00:00'))
      item['date_published'] = dt_pub.isoformat()
      item['_timestamp'] = dt_pub.timestamp()
      item['_display_date'] = dt_pub.strftime('%b %-d, %Y')

  if not item.get('date_modified'):
    it = soup.find('meta', attrs={"name": "article:modified_time"})
    if it:
      dt_mod = datetime.fromisoformat(it['content'].replace('Z', '+00:00'))
      item['date_modified'] = dt_mod.isoformat()

  if not item.get('author'):
    it = soup.find('meta', attrs={"name": "author"})
    if it:
      item['author'] = {}
      item['author']['name'] = it['content'].replace('By ', '')

  if not item.get('image'):
    it = soup.find('meta', attrs={"property": "og:image"})
    if it:
      item['_image'] = it['content']

  if not item.get('summary'):
    it = soup.find('meta', attrs={"name": "description"})
    if it:
      item['summary'] = it['content']

  article_body = soup.find(attrs={"itemprop": "articleBody"})
  if article_body:
    el = soup.find(class_='image__lede')
    if el:
      article_body.insert(0, el)
    elif item.get('_image'):
      new_el = BeautifulSoup(utils.add_image(item['_image']), 'html.parser')
      article_body.insert(0, new_el)

    el = article_body.find(class_='source')
    if el:
      el.find_next_sibling('p').insert(0, el.strong)

    for el in article_body.find_all(class_="image"):
      img = el.find('img')
      caption = ''
      img_caption = el.find(attrs={"itemprop": "caption"})
      if img_caption and img_caption.string:
        caption += img_caption.string
      img_credit = el.find(class_='image__credit')
      if img_credit and img_credit.string:
        if caption:
          caption += ' '
        caption += '[{}]'.format(img_credit.string)
      new_el = BeautifulSoup(utils.add_image(img['src'], caption), 'html.parser')
      el.insert_after(new_el)
      el.decompose()

    item['content_html'] = str(article_body)
  else:
    logger.warning('unable to parse content in ' + url)
    item['content_html'] = ''
    if item.get('_image'):
      item['content_html'] += utils.add_image(item['_image'])
    item['content_html'] += '<p>{}</p>'.format(item['summary'])   
  return item

def get_content_from_initial_state(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(article_html)

  m = re.search(r'<script>\s*window\.__INITIAL_STATE__ = (.+);\s+window.', article_html)
  if m:
    try:
      initial_state = json.loads(m.group(1))
    except:
      logger.warning('Error loading initial_state data from ' + url)
      return None

  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(initial_state, file, indent=4)

  slug = urlsplit(url).path
  item = get_item_info(initial_state[slug])

  first_element = True
  item['content_html'] = ''
  region = initial_state[slug]['regions']
  region_key = region[region['type']]
  for rc in initial_state[region_key]['regionContents']:
    rc_key = rc[rc['type']]
    for zone in initial_state[rc_key]['zones']:
      zone_key = zone[zone['type']]
      for zc in initial_state[zone_key]['zoneContents']:
        zc_key = zc[zc['type']]
        if not initial_state[zc_key].get('type'):
          logger.warning('skipping zoneContents {} in {}'.format(zc_key, url))
          continue
        zc_type = initial_state[zc_key]['type']
        if zc_type == 'element':
          # Remove the feed image if there's a lead photo/video
          if first_element:
            if re.search(r'^(gallery|image|video)', initial_state[zc_key]['contentType']):
              item['_image'] = item['image']
              del item['image']
          item['content_html'] += process_element(initial_state[zc_key], url, save_debug)
          first_element = False
        elif zc_type == 'string':
          str_contents = initial_state[zc_key]['stringContents']
          if isinstance(str_contents[str_contents['type']], dict):
            for txt in str_contents[str_contents['type']]['formattedText']:
              item['content_html'] += '<p>{}</p>'.format(txt)
          else:
            logger.warning('string is a list {} in {}'.format(str(str_contents[str_contents['type']]), url))
  return item

def get_live_news_content(url, args, save_debug=False):
  livestory_id = url.split('/')[-1]
  print(livestory_id)
  headers = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"90\", \"Google Chrome\";v=\"90\"",
    "sec-ch-ua-mobile": "?0",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "sec-gpc": "1",
    "x-api-key": "P7LEOCujzt2RqSaWBeImz1spIoLq7dep7x983yQc",
    "x-graphql-query-uuid": "livestory---PostsWithGraph{\"livestory_id\":\"h_dd3c2644be053a63af6b1bf86dc61ba8\",\"startId\":null}---0d02c8bfc7cb62ae01f7de7f444069bfda2614c90952730601e1f22df0641fe1"
  }
  gql_query = '{\"operationName\":\"PostsWithGraph\",\"variables\":{\"livestory_id\":\"h_dd3c2644be053a63af6b1bf86dc61ba8\",\"startId\":null},\"query\":\"query PostsWithGraph($livestory_id: String) {\\n  getLivestoryWebData(livestory_id: $livestory_id) {\\n    id\\n    lastPublishDate\\n    lastPublishDateFormatted\\n    activityStatus\\n    pinnedPosts {\\n      id\\n      lastPublishDate\\n      __typename\\n    }\\n    unpinnedPosts {\\n      id\\n      sourceId\\n      lastPublishDate\\n      lastPublishDateFormatted\\n      headline\\n      byline\\n      content\\n      tags\\n      __typename\\n    }\\n    tags\\n    __typename\\n  }\\n}\\n\"}'

  livestory_json = utils.post_url('https://data.api.cnn.io/graphql', gql_query, headers)
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(livestory_json, file, indent=4)
  return None

def get_content(url, args, save_debug=False):
  if '/live-news/' in url:
    return None
  if re.search(r'\/(style|travel)\/', url):
    return get_content_from_initial_state(url, args, save_debug)
  if re.search(r'\/(cnn-underscored|videos)\/', url):
    return get_content_from_html(url, args, save_debug)

  split_url = urlsplit(url)
  json_url = 'https://www.cnn.com{}:*.json'.format(split_url.path)
  article_json = utils.get_url_json(json_url)
  if not article_json:
    return get_content_from_html(url, args, save_debug)
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(article_json, file, indent=4)

  item = get_item_info(article_json)

  first_element = True
  content_html = ''
  for pages in article_json['pageContents']:
    for page in pages:
      if page:
        for zone in page['zoneContents']:
          if isinstance(zone, list):
            if len(zone) >= 1 and zone[0]:
              content_html += '<p>'
              for z in zone:
                content_html += z
              content_html += '</p>'
            continue
          if zone.get('type'):
            # Note: "containers" seem to be ads, related articles, etc.
            if zone['type'] == 'element':
              # Remove the feed image if there's a lead photo/video
              if first_element:
                if re.search(r'^(gallery|image|video)', zone['contentType']):
                  item['_image'] = item['image']
                  del item['image']
              else:
                if item.get('image'):
                  content_html += utils.add_image(item['image'])
                  item['_image'] = item['image']
                  del item['image']
              content_html += process_element(zone, json_url, save_debug)
              first_element = False
          else:
            if zone.get('formattedText'):
              for text in zone['formattedText']:
                content_html += '<p>{}</p>'.format(text)
  item['content_html'] = content_html

  return item

def get_feed(args, save_debug=False):
  n = 0
  items = []
  feed = rss.get_feed(args, save_debug)
  for feed_item in feed['items']:
    # Skip non- cnn.com urls
    # Skip coupons/deals
    # Skip podcasts - they have their own rss feeds
    #print(feed_item['url'])
    if not 'cnn.com' in feed_item['url'] or re.search(r'coupons\.cnn\.com|\/podcasts\/|\/specials\/', feed_item['url']):
      if save_debug:
        logger.debug('skipping ' + feed_item['url'])
      continue
    
    if save_debug:
      logger.debug('getting content for ' + feed_item['url'])
    item = get_content(feed_item['url'], args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed['items'] = items.copy()
  return feed