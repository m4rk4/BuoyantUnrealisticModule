import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import urlsplit

import utils

import logging
logger = logging.getLogger(__name__)

def get_chart_content(url, args, save_debug=False):
  page_html = utils.get_url_html(url)
  if not page_html:
    return None
  soup = BeautifulSoup(page_html, 'html.parser')
  el = soup.find(id='charts')
  if el and el.has_attr('data-charts'):
    charts_json = json.loads(unescape(el['data-charts']))
    if save_debug:
      utils.write_file(charts_json, './debug/charts.json')

    if not el['data-chart-date'] in url:
      if not url.endswith('/'):
        url += '/'
      url += el['data-chart-date']

    item = {}
    item['id'] = url
    item['url'] = url
    item['title'] = '{} - {}'.format(el['data-page-title'], el['data-chart-date-formatted'])

    # The chart date is the end of the week (Sat), so the published date is 6 days prior
    dt_pub = datetime.fromisoformat(el['data-chart-date']) - timedelta(days=6)
    item['date_published'] = dt_pub.isoformat()
    item['_timestamp'] = dt_pub.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt_pub.strftime('%b'), dt_pub.day, dt_pub.year)

    it = soup.find('img', class_='charts__header__promo__title_logo')
    if it:
      item['_image'] = it['src']
    else:
      item['_image'] = el['data-chart-logo']

    item['content_html'] = utils.add_image(item['_image'])
    item['content_html'] += '<p>For the week ending {}</p>'.format(el['data-chart-date-formatted'])
    item['content_html'] += '<table><tr><th>&nbsp;</th><th>&nbsp;</th><th style="text-align:center;">Last week</th><th style="text-align:center;">Peak</th><th style="text-align:center;">Wks on chart</th></tr><th>&nbsp;</th>'
    for data in charts_json:
      item['content_html'] += '<tr><td style="text-align:center; font-size:2em;">{}</td>'.format(data['rank'])
      artist = ''
      title = ''
      if data.get('artist_name'):
        artist = data['artist_name']
        if data.get('artist_url'):
          artist = '<a href="https://www.billboard.com{}">{}</a>'.format(data['artist_url'], data['artist_name'])
      if data.get('title'):
        title = data['title']
        m = re.search(r'([^\/]+)\s\/\s(@.+)', data['title'])
        if m:
          title = m.group(1)
          artist = m.group(2)
        if data.get('title_content_url'):
          title = '<a href="https://www.billboard.com{}">{}</a>'.format(data['title_content_url'], title)
      if title and artist:
        item['content_html'] += '<td style="padding:0.5em 0 0.5em 1em;"><b>{}</b><br/>{}</td>'.format(title, artist)
      else:
        item['content_html'] += '<td style="padding:0.5em 0 0.5em 1em;"><b>{}</b></td>'.format(title)
      if data['history'].get('last_week'):
        item['content_html'] += '<td style="text-align:center;">{}</td>'.format(data['history']['last_week'])
      else:
        item['content_html'] += '<td style="text-align:center;">-</td>'
      item['content_html'] += '<td style="text-align:center;">{}</td>'.format(data['history']['peak_rank'])
      item['content_html'] += '<td style="text-align:center;">{}</td>'.format(data['history']['weeks_on_chart'])
      img_src = ''
      for images in ['title_images', 'artist_images']:
        if data.get(images) and not img_src:
          for size in ['small', 'medium', 'detail-med']:
            if size in data[images]['sizes']:
              img_src = data[images]['sizes'][size]['Name']
              break
      if img_src:
        item['content_html'] += '<td style="text-align:center;"><img height="87px" src="https://charts-static.billboard.com{}" /></td></tr>'.format(img_src)
      else:
        item['content_html'] += '<td style="height:87px; text-align:center;">&nbsp;</td></tr>'
    item['content_html'] += '</table>'

  else:
    el = soup.find(class_='print-chart__week')
    dt = datetime.strptime(el.get_text().strip(), 'The week of %B %d, %Y')
    date = dt.strftime('%Y-%m-%d')
    if not date in url:
      if not url.endswith('/'):
        url += '/'
      url += date
    formatted_date = '{} {}, {}'.format(dt.strftime('%B'), dt.day, dt.year)

    item = {}
    item['id'] = url
    item['url'] = url

    el = soup.find('meta', attrs={"name": "title"})
    item['title'] = '{} - {}'.format(unescape(el['content']), formatted_date)

    dt_pub = dt -  - timedelta(days=6)
    item['date_published'] = dt_pub.isoformat()
    item['_timestamp'] = dt_pub.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt_pub.strftime('%b'), dt_pub.day, dt_pub.year)

    el = soup.find('img', class_='print-chart__logo')
    item['_image'] = el['src']

    item['content_html'] = ''
    item['content_html'] = utils.add_image(item['_image'])
    item['content_html'] += '<p>For the week ending {}</p>'.format(formatted_date)
    item['content_html'] += '<table><tr><th>&nbsp;</th><th>&nbsp;</th><th style="text-align:center;">Last week</th><th style="text-align:center;">Peak</th><th style="text-align:center;">Wks on chart</th></tr><th>&nbsp;</th>'
    for el in soup.find_all(class_='chart-list-item', attrs={"data-rank": True}):
      item['content_html'] += '<tr><td style="text-align:center; font-size:2em;">{}</td>'.format(el['data-rank'])
      if el['data-title']:
        it = el.find(class_='chart-list-item__title')
        if it.a:
          title = '<a href="https://www.billboard.com{}">{}</a>'.format(it.a['href'], el['data-title'])
        else:
          title = el['data-title']
      else:
        title = ''
      if el['data-artist']:
        it = el.find(class_='chart-list-item__artist')
        if it.a:
          artist = '<a href="https://www.billboard.com{}">{}</a>'.format(it.a['href'], el['data-artist'])
        else:
          artist = el['data-artist']
      else:
        artist = ''
      if title and artist:
        item['content_html'] += '<td style="padding:0.5em 0 0.5em 1em;"><b>{}</b><br/>{}</td>'.format(title, artist)
      else:
        item['content_html'] += '<td style="padding:0.5em 0 0.5em 1em;"><b>{}</b></td>'.format(title)
      it = el.find(class_='chart-list-item__ministats')
      m = re.search(r'([\d\-]+)\s+Last\s+([\d\-]+)\s+Peak\s+([\d\-]+)\s+Weeks', it.get_text().strip())
      item['content_html'] += '<td style="text-align:center;">{}</td>'.format(m.group(1))
      item['content_html'] += '<td style="text-align:center;">{}</td>'.format(m.group(2))
      item['content_html'] += '<td style="text-align:center;">{}</td>'.format(m.group(3))
      img_src = ''
      #it = el.find('img', attrs={"data-srcset": True})
      it = el.find(class_='chart-list-item__image')
      if it:
        if it.has_attr('data-srcset'):
          img_src = utils.image_from_srcset(it['data-srcset'], 87)
        elif it.has_attr('data-src'):
          img_src = it['data-src']
        elif it.has_attr('src') and it['src'].startswith('https'):
          img_src = it['src']
      if img_src:
        item['content_html'] += '<td style="text-align:center;"><img height="87px" src="{}" /></td></tr>'.format(img_src)
      else:
        item['content_html'] += '<td style="height:87px; text-align:center;">&nbsp;</td></tr>'
    item['content_html'] += '</table>'
  return item

def get_video_item(video_id, args, save_debug=False):
  jwp_json = utils.get_url_json(
    'https://content.jwplatform.com/feeds/{}.json?page_domain=www.billboard.com'.format(video_id))
  if not jwp_json:
    logger.warning('unable to get video details for video_id ' + video_id)
    None
  if save_debug:
    utils.write_file(jwp_json, './debug/video.json')

  video_json = jwp_json['playlist'][0]
  item = {}
  item['id'] = video_id
  item['url'] = video_json['link']
  item['title'] = video_json['title']

  tz_est = pytz.timezone('US/Eastern')
  dt_loc = datetime.fromtimestamp(video_json['pubdate'])
  dt_utc = tz_est.localize(dt_loc).astimezone(pytz.utc)
  item['date_published'] = dt_utc.isoformat()
  item['_timestamp'] = dt_utc.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt_utc.strftime('%b'), dt_utc.day, dt_utc.year)

  item['tags'] = video_json['tags'].split(',')
  item['summary'] = video_json['description']

  poster = utils.closest_dict(video_json['images'], 'width', 720)
  item['_image'] = poster['src']

  videos = []
  for video in video_json['sources']:
    if video['type'] == 'video/mp4':
      videos.append(video)
  video = utils.closest_dict(videos, 'height', 360)
  item['_video'] = video['file']

  item['content_html'] = utils.add_video(video['file'], 'video/mp4', poster['src'])
  item['content_html'] += '<p>{}</p>'.format(video_json['description'])
  return item

def get_video_content(url, args, save_debug=False):
  page_html = utils.get_url_html(url)
  if not page_html:
    return None
  soup = BeautifulSoup(page_html, 'html.parser')
  video_content = soup.find(class_='video-holder')
  if not video_content:
    return None
  if not video_content.has_attr('data-initial-video'):
    return None
  video_json = json.loads(unescape(video_content['data-initial-video']))
  if save_debug:
    utils.write_file(video_json, './debug/debug.json')
  if not video_json.get('video_id'):
    return None
  return get_video_item(video_json['video_id'], args, save_debug)

def get_content(url, args, save_debug=False):
  split_url = urlsplit(url)
  if split_url.path.startswith('/video/'):
    return get_video_content(url, args, save_debug)
  elif split_url.path.startswith('/charts/'):
    return get_chart_content(url, args, save_debug)

  json_url = '{}://{}/json{}'.format(split_url.scheme, split_url.netloc, split_url.path)
  article_json = utils.get_url_json(json_url)
  if not article_json:
    return None
  if save_debug:
    utils.write_file(article_json, './debug/debug.json')
  article_data = article_json['data']

  item = {}
  item['id'] = article_data['id']
  item['url'] = article_data['link']
  item['title'] = article_data['title']

  dt = datetime.fromisoformat(article_data['dateGmt'] + '+00:00')
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(article_data['modifiedGmt'] + '+00:00')
  item['date_modified'] = dt.isoformat()

  authors = []
  for author in article_data['author']:
    authors.append(author['name'])
  if authors:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  item['tags'] = []
  for it in article_data['artists']['nodes']:
    item['tags'].append(it['name'])
  for it in article_data['categories']['edges']:
    if it['node'].get('name'):
      item['tags'].append(it['node']['name'])
    elif it['node'].get('slug'):
      item['tags'].append(it['node']['slug'])
  #for it in article_data['tags']['edges']:
  #  item['tags'].append(it['node']['name'])

  content_html = ''
  if article_data.get('featuredImage'):
    image = utils.closest_dict(article_data['featuredImage']['mediaDetails']['filteredSizes'], 'width', 1000)
    item['_image'] = image['sourceUrl']
    if article_data['__typename'] == 'Post' and article_data['parsedContent'][0]['type'] != 'image':
      caption = []
      it = article_data['featuredImage'].get('caption')
      if it and it.strip():
        it = it.strip()
        if it:
          if it.startswith('<p>') and it.endswith('</p>'):
            it = it[3:-4]
          caption.append(it)
      it = article_data['featuredImage'].get('credit')
      if it:
        it = it.strip()
        if it:
          caption.append(it)
      content_html += utils.add_image(image['sourceUrl'], ' | '.join(caption))

  item['summary'] = article_data['seoDescription']

  if article_data['__typename'] == 'Post':
    for content in article_data['parsedContent']:
      if content['type'] == 'html':
        if content['params']['tag'] == 'hr':
          content_html += '<hr/>'
        else:
          content_html +='<{0}>{1}</{0}>'.format(content['params']['tag'], content['params']['content'])

      elif content['type'] == 'image':
        caption = []
        it = content['params'].get('caption')
        if it and it.strip():
          it = it.strip()
          if it:
            if it.startswith('<p>') and it.endswith('</p>'):
              it = it[3:-4]
            caption.append(it)
        it = content['params'].get('credit')
        if it:
          it = it.strip()
          if it:
            caption.append(it)
        image = utils.closest_dict(content['params']['sizes'], 'width', 1000)
        content_html += utils.add_image(image['path'], ' | '.join(caption))

      elif content['type'] == 'video':
        video = get_video_item(content['params']['id'], {}, save_debug)
        if video:
          content_html += utils.add_video(video['_video'], 'video/mp4', video['_image'], video['title'])

      elif content['type'] == 'iframe':
        if 'youtube.com' in content['params']['src']:
          content_html += utils.add_youtube(content['params']['src'])
        else:
          logger.warning('unhandled iframe src {} in {}'.format(content['params']['src'], url))

      elif content['type'] == 'oembed':
        if content['params']['type'] == 'twitter':
          m = re.findall(r'href="(https:\/\/twitter\.com\/[^\/]+\/status\/\d+)', content['params']['content'])
          if not m:
            logger.warning('unable to parse twitter link in ' + url)
          content_html += utils.add_twitter(m[-1])

        elif content['params']['type'] == 'instagram':
          m = re.search(r'data-instgrm-permalink="([^"]+)"', content['params']['content'])
          if not m:
            logger.warning('unable to parse instagram link in ' + url)
            continue
          content_html += utils.add_instagram(m.group(1))

        elif content['params']['type'] == 'youtube':
          m = re.search(r'src="(https:\/\/www\.youtube\.com\/embed\/[a-zA-Z0-9_-]{11})', content['params']['content'])
          if not m:
            logger.warning('unable to parse youtube link in ' + url)
            continue
          content_html += utils.add_youtube(m.group(1))

        else:
          logger.warning('unhandled oembed type {} in {}'.format(content['params']['type'], url))

      elif content['type'] == 'readmore':
        continue

      else:
        logger.warning('unhandled content type {} in {}'.format(content['type'], url))

  elif article_data['__typename'] == 'Gallery':
    for content in article_data['slides']['edges']:
      if content['__typename'] == 'SlideTypeEdge':
        slide = content['node']
        image = utils.closest_dict(slide['image']['mediaDetails']['filteredSizes'], 'width', 1000)
        caption = slide.get('credit')
        if caption:
          caption = caption.strip()
        else:
          caption = ''
        content_html += utils.add_image(image['sourceUrl'], caption)
        if slide.get('title'):
          content_html += '<h3>{}</h3>'.format(slide['title'])
        content_html += slide['caption']
        if slide.get('otherEmbedCode'):
          m = re.findall(r'href="(https:\/\/twitter\.com\/[^\/]+\/status\/\d+)', slide['otherEmbedCode'])
          if m:
            content_html += utils.add_twitter(m[-1])
          else:
            m = re.search(r'data-instgrm-permalink="([^"]+)"', slide['otherEmbedCode'])
            if m:
              content_html += utils.add_instagram(m.group(1))
            else:
              m = re.search(r'src="(https:\/\/www\.youtube\.com\/embed\/[a-zA-Z0-9_-]{11})', slide['otherEmbedCode'])
              if m:
                content_html += utils.add_youtube(m.group(1))
              else:
                logger.warning('unhandled otherEmbedCode in ' + url)
      else:
        logger.warning('unhandled gallery type {} in {}'.format(content['__typename'], url))

  item['content_html'] = content_html
  return item

def get_chart_feed(args, save_debug=False):
  items = []
  split_url = urlsplit(args['url'])
  if split_url.path == '/charts' or split_url.path == '/charts/':
    page_html = utils.get_url_html(args['url'])
    if not page_html:
      return None
    soup = BeautifulSoup(page_html, 'html.parser')
    for a in soup.find_all('a', class_='chart-panel__link', attrs={"data-chart-code": True}):
      url = 'https://www.billboard.com' + a['href']
      if save_debug:
        logger.debug('getting content for ' + url)
      item = get_chart_content(url, args, save_debug)
      if item:
        if utils.filter_item(item, args) == True:
          items.append(item)
  else:
    if save_debug:
      logger.debug('getting content for ' + args['url'])
    item = get_chart_content(args['url'], args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)

  feed = utils.init_jsonfeed(args)
  del feed['items']
  feed['items'] = items.copy()
  return feed

def get_video_feed(args, save_debug=False):
  page_html = utils.get_url_html(args['url'])
  if not page_html:
    return None
  soup = BeautifulSoup(page_html, 'html.parser')
  el = soup.find(id='videoHub')
  if not el:
    return None
  if not el.has_attr('data-series'):
    return None
  page_json = json.loads(unescape(el['data-series']))
  if save_debug:
    utils.write_file(page_json, './debug/videos.json')

  items = []
  for series in page_json:
    for video in series['videos']:
      video_url = 'https://www.billboard.com' + video['path']
      # Check age
      if args.get('age'):
        item = {}
        tz_est = pytz.timezone('US/Eastern')
        if video.get('date'):
          dt_loc = datetime.fromisoformat(video['date'])
        else:
          dt_loc = datetime.fromtimestamp(video['publishDate'])
        dt_utc = tz_est.localize(dt_loc).astimezone(pytz.utc)
        item['_timestamp'] = dt_utc.timestamp()
        if not utils.check_age(item, args):
          if save_debug:
            logger.debug('skipping ' + video_url)
          continue

      if save_debug:
        logger.debug('getting content for ' + video_url)
      if video.get('video_id'):
        item = get_video_item(video['video_id'], args, save_debug)
      else:
        logger.warning('no video_id for ' + video_url)
        continue
      if item:
        item['url'] = video_url
        if utils.filter_item(item, args) == True:
          items.append(item)

  # sort by date
  items = sorted(items, key=lambda i: i['_timestamp'], reverse=True)

  feed = utils.init_jsonfeed(args)
  del feed['items']
  if 'max' in args:
    n = int(args['max'])
    feed['items'] = items[n:].copy()
  else:
    feed['items'] = items.copy()
  return feed

def get_feed(args, save_debug=False):
  split_url = urlsplit(args['url'])

  if split_url.path == '/videos' or split_url.path == '/videos/':
    return get_video_feed(args, save_debug)
  elif split_url.path == '/charts' or split_url.path.startswith('/charts/'):
    return get_chart_feed(args, save_debug)
  elif split_url.path.startswith('/series/'):
    json_url = '{}://{}/fe_data{}'.format(split_url.scheme, split_url.netloc, split_url.path)
    if json_url.endswith('/'):
      json_url += '1'
    else:
      json_url += '/1'
    page_json = utils.get_url_json(json_url)
    if page_json:
      posts = page_json
  elif split_url.path.startswith('/music/'):
    artist = split_url.path.split('/')[2]
    json_url = '{}://{}/fe_data/news/artist/{}/10/0'.format(split_url.scheme, split_url.netloc, artist)
    page_json = utils.get_url_json(json_url)
    if page_json:
      posts = page_json
  else:
    json_url = '{}://{}/json{}'.format(split_url.scheme, split_url.netloc, split_url.path)
    page_json = utils.get_url_json(json_url)
    if page_json:
      posts = page_json['page']['contentFeed']['nodes']

  if not page_json:
    return None
  if save_debug:
    utils.write_file(page_json, './debug/debug.json')

  n = 0
  items = []
  for post in posts:
    # Check age
    if args.get('age'):
      item = {}
      tz_est = pytz.timezone('US/Eastern')
      if post.get('date'):
        dt_loc = datetime.fromisoformat(post['date'])
      else:
        dt_loc = datetime.fromtimestamp(post['publishDate'])
      dt_utc = tz_est.localize(dt_loc).astimezone(pytz.utc)
      item['_timestamp'] = dt_utc.timestamp()
      if not utils.check_age(item, args):
        continue

    post_url = post.get('link')
    if not post_url:
      post_url = 'https://www.billboard.com' + post['path']

    if save_debug:
      logger.debug('getting content from ' + post_url)

    post_type = post.get('__typename')
    if not post_type:
      if '/video/' in post_url:
        post_type = 'BrightcoveVideo'
      else:
        post_type = 'Post'

    if post_type == 'BrightcoveVideo':
      video_id = post.get('videoId')
      if not video_id:
        video_id = post['video_id']
      item = get_video_item(video_id, args, save_debug)
      if item:
        item['url'] = post_url
    elif post_type == 'Post':
      item = get_content(post_url, args, save_debug)
    else:
      logger.warning('unhandled post type {} in {}'.format(post['__typename'], post['link']))
      continue

    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break

  feed = utils.init_jsonfeed(args)
  del feed['items']
  feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True).copy()
  return feed