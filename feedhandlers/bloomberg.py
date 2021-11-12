import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def resize_image(img_src):
  return re.sub(r'[\d-]+x[\d-]+.jpg', '1024x-1.jpg', img_src)

def get_bb_url(url, get_json=False):
  headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    "dnt": "1",
    "pragma": "no-cache",
    "sec-ch-ua": "\"Google Chrome\";v=\"95\", \"Chromium\";v=\"95\", \";Not A Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "Windows",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "sec-gpc": "1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36"
  }
  if '/localhost' in config.server:
    use_proxy = False
  else:
    use_proxy = True
  if get_json:
    return utils.get_url_json(url, headers=headers, use_proxy=use_proxy)
  return utils.get_url_html(url, headers=headers, use_proxy=use_proxy)

def add_video(video_id):
  video_json = get_bb_url('https://www.bloomberg.com/multimedia/api/embed?id=' + video_id, True)
  if video_json:
    if video_json.get('description'):
      caption = video_json['description']
    elif video_json.get('title'):
      caption = video_json['title']
    poster = resize_image('https:' + video_json['thumbnail']['baseUrl'])
    return utils.add_video(video_json['downloadURLs']['600'], 'video/mp4', poster, caption)

def get_video_content(url, args, save_debug):
  if args and 'embed' in args:
    video_id = url
    bb_json = None
  else:
    bb_html = get_bb_url(url)
    if not bb_html:
      return None
    if save_debug:
      utils.write_file(bb_html, './debug/debug.html')

    m = re.search(r'window\.__PRELOADED_STATE__ = ({.+});', bb_html)
    if not m:
      logger.warning('unable to parse __PRELOADED_STATE__ in '+ url)
      return None
    bb_json = json.loads(m.group(1))
    if save_debug:
      utils.write_file(bb_json, './debug/debug.json')
    video_id = bb_json['quicktakeVideo']['videoStory']['video']['bmmrId']

  video_json = get_bb_url('https://www.bloomberg.com/multimedia/api/embed?id=' + video_id, True)
  if not video_json:
    return None
  if save_debug:
    utils.write_file(video_json, './debug/video.json')

  item = {}
  if bb_json:
    item['id'] = bb_json['quicktakeVideo']['videoStory']['id']
    item['url'] = bb_json['quicktakeVideo']['videoStory']['url']
  else:
    item['id'] = video_json['id']
    item['url'] = video_json['downloadURLs']['600']

  item['title'] = video_json['title']

  dt = datetime.fromtimestamp(int(video_json['createdUnixUTC'])).replace(tzinfo=timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  if video_json.get('peopleCodes'):
    authors = []
    for key, val in video_json['peopleCodes'].items():
      authors.append(val.title())
    if authors:
      item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
  if not item['author'].get('name'):
    item['author']['name'] = 'Bloomberg News'

  if video_json.get('metadata') and video_json['metadata'].get('contentTags'):
    item['tags'] = []
    for tag in video_json['metadata']['contentTags']:
      item['tags'].append(tag['id'])

  item['_image'] = resize_image('https:' + video_json['thumbnail']['baseUrl'])
  item['_video'] = video_json['downloadURLs']['600']
  item['_audio'] = video_json['audioMp3Url']

  item['summary'] = video_json['description']

  if args and 'embed' in args:
    item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'], video_json['description'])
  else:
    item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'])
    item['content_html'] += '<p>{}</p>'.format(item['summary'])
    if bb_json['quicktakeVideo']['videoStory']['video'].get('transcript'):
      item['content_html'] += '<h3>Transcript</h3><p>{}</p>'.format(bb_json['quicktakeVideo']['videoStory']['video']['transcript'].replace('\n', ''))
  return item

def get_content(url, args, save_debug):
  if '/videos/' in url:
    return get_video_content(url, '', args, save_debug)

  api_url = ''
  split_url = urlsplit(url)
  m = re.search(r'\/articles\/(.*)', split_url.path)
  if m:
    api_url = 'https://www.bloomberg.com/javelin/api/transporter/' + m.group(1)
  else:
    m = re.search(r'\/features\/(.*)', split_url.path)
    if m:
      api_url = 'https://www.bloomberg.com/javelin/api/feature_transporter/' + m.group(1)
  if not api_url:
    logger.warning('unsupported url ' + url)

  #bb_json = utils.read_json_file('./debug/debug.json')
  #if not bb_json:
  bb_json = get_bb_url(api_url, True)
  if not bb_json:
    return None
  if save_debug:
    utils.write_file(bb_json, './debug/debug.json')

  item = {}
  item['id'] = bb_json['metadata']['content']['id']
  item['url'] = bb_json['metadata']['content']['canonical']
  item['title'] = bb_json['metadata']['content']['textHeadline']

  dt = datetime.fromisoformat(bb_json['metadata']['content']['publishedAt'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  item['author']['name'] = bb_json['metadata']['content']['byline']

  item['tags'] = bb_json['metadata']['content']['wssTags'].copy()

  item['summary'] = bb_json['metadata']['content']['twitterText']

  item['content_html'] = ''

  soup = BeautifulSoup(bb_json['html'], 'html.parser')

  el = soup.find('ul', class_='abstract-v2')
  if el:
    item['content_html'] += str(el)

  el = soup.find('figure', class_='lede')
  if not el:
    el = soup.find(class_=re.compile(r'lede-.*image|image-.*lede'))
  if el:
    print(el)
    img_src = ''
    if el.img:
      img_src = resize_image(el.img['data-native-src'])
    elif el.find(class_='bg-crop'):
      it = el.find(style=re.compile('background-image'))
      if it:
        m = re.search(r'background-image: url\(\'([^\']+)\'', it['style'])
        if m:
          img_src = m.group(1)
    if img_src:
      caption = []
      it = el.find(class_=re.compile(r'caption'))
      if it and it.get_text().strip():
        caption.append(it.get_text().strip())
      it = el.find(class_=re.compile('credit'))
      if it and it.get_text().strip():
        caption.append(it.get_text().strip())
      item['content_html'] += utils.add_image(img_src, ' | '.join(caption))
    else:
      logger.warning('unable to determine lede image src in ' + url)

  else:
    el = soup.find(class_=re.compile('lede-video'))
    if el:
      it = el.find(class_='video-player__container')
      if it:
        video = get_video_content(it['data-bmmrid'], {"embed": True}, save_debug)
        if video:
          item['content_html'] += video['content_html']
        else:
          item['content_html'] += '<h4>Video: {}</h4>'.format(it['data-url'])
      else:
        logger.warning('unable to determine lede video src in ' + url)

  el = soup.find('script', attrs={"data-component-props":re.compile(r'ArticleBody|FeatureBody')})
  if not el:
    return item

  article_json = json.loads(el.string)
  if save_debug:
    utils.write_file(article_json, './debug/content.json')

  body = BeautifulSoup(article_json['body'], 'html.parser')
  #item['content_html'] = str(body)

  for el in body.find_all(attrs={"data-ad-placeholder": "Advertisement"}):
    el.decompose()

  for el in body.find_all(class_=re.compile(r'-footnotes|-newsletter|page-ad|-recirc')):
    el.decompose()

  for el in body.find_all('a', href=re.compile(r'^\/')):
    el['href'] = 'https://www.bloomberg.com' + el['href']

  for el in body.find_all('meta'):
    el.decompose()

  for el in body.find_all('figure'):
    new_html = ''
    if el.get('data-image-type') == 'chart' and el.get('data-widget-url'):
      chart = get_bb_url(el['data-widget-url'])
      if chart:
        m = re.search(r'toaster\.factory\(el, ({.*}), {"brand"', chart)
        if m:
          chart_json = json.loads(m.group(1))
          utils.write_file(chart_json, './debug/charts.json')
          caption = []
          if chart_json.get('subtitle'):
            caption.append(chart_json['subtitle'])
          if chart_json.get('source'):
            caption.append(chart_json['source'])
          if chart_json.get('footnote'):
            caption.append(chart_json['footnote'])
          if chart_json['config']['responsive_images'].get('light'):
            img_src = chart_json['config']['responsive_images']['light']['url']
          elif chart_json['config']['responsive_images'].get('dark'):
            img_src = chart_json['config']['responsive_images']['dark']['url']
          new_html = utils.add_image(img_src, ' | '.join(caption))

    elif el.get('data-image-type') == 'photo' or el.get('data-type') == 'image':
      img_src = resize_image(el.img['data-native-src'])
      caption = []
      it = el.find(class_='caption')
      if it and it.get_text().strip():
        caption.append(it.get_text().strip())
      it = el.find(class_='credit')
      if it and it.get_text().strip():
        caption.append(it.get_text().strip())
      new_html = utils.add_image(img_src, ' | '.join(caption))

    if new_html:
      new_el = BeautifulSoup(new_html, 'html.parser')
      el.insert_after(new_el)
      el.decompose()

  for el in body.find_all('div', class_='thirdparty-embed'):
    new_html = ''
    if el.blockquote and ('twitter-tweet' in el.blockquote['class']):
      m = re.findall('https:\/\/twitter\.com\/[^\/]+\/statuse?s?\/\d+', str(el.blockquote))
      new_html += utils.add_embed(m[-1])

    if new_html:
      new_el = BeautifulSoup(new_html, 'html.parser')
      el.insert_after(new_el)
      el.decompose()

  item['content_html'] += str(body)
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)