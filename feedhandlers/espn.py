import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import utils

import logging
logger = logging.getLogger(__name__)

def resize_image(img_src, width=1000):
  split_url = urlsplit(img_src)
  return 'https://a1.espncdn.com/combiner/i?img={}&w={}&cquality=80&location=origin&format=jpg'.format(quote_plus(split_url.path), width)

def get_image(image):
  caption = []
  if image.get('caption'):
    caption.append(image['caption'])
  if image.get('credit'):
    caption.append(format(image['credit']))
  return image['url'], ' | '.join(caption)

def get_video(video):
  vid_src = video['links']['mobile']['source']['href']
  vid_type = 'video/mp4'
  poster = resize_image(video['thumbnail'])
  # poster = video['posterImages']['full']['href']
  caption = []
  if video.get('caption'):
    caption.append(video['caption'])
  if video.get('credit'):
    caption.append(format(video['credit']))
  return vid_src, vid_type, poster, ' | '.join(caption)

def get_story(story_json, args, save_debug=False):
  item = {}
  item['id'] = story_json['id']
  url = story_json['links']['web']['href']
  item['url'] = url
  if story_json.get('title'):
    item['title'] = story_json['title']
  elif story_json.get('headline'):
    item['title'] = story_json['headline']
  else:
    logger.warning('unknown title for ' + url)

  dt = datetime.fromisoformat(story_json['published'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(story_json['lastModified'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()
  if args.get('age'):
    if not utils.check_age(item, args):
      if save_debug:
        logger.debug('skipping old article ' + url)
      return None

  item['author'] = {}
  if story_json.get('byline'):
    item['author']['name'] = story_json['byline']
  elif story_json.get('source'):
    item['author']['name'] = story_json['source']
  else:
    item['author']['name'] = 'ESPN'

  if story_json.get('keywords'):
    item['tags'] = story_json['keywords'].copy()
  else:
    item['tags'] = []
    for tag in story_json['categories']:
      if tag.get('description'):
        item['tags'].append(tag['description'])

  if story_json.get('images'):
    item['_image'] = story_json['images'][0]['url']

  item['summary'] = story_json['description']

  story_soup = BeautifulSoup(story_json['story'], 'html.parser')
  if save_debug:
    utils.write_file(str(story_soup), './debug/debug.html')

  for el in story_soup.find_all(class_='floatleft'):
    el['style'] = 'float:left; margin-top:0.25em; margin-right:0.5em;'
    it = story_soup.new_tag('div')
    it['style'] = 'clear:left;'
    a = el.find_next('h2')
    if not a:
      a = el.find_next('p')
    a.insert_after(it)

  for el in story_soup.find_all('img', src=re.compile(r'gn-arrow|rd-arrow|sw_ye_40')):
    it = story_soup.new_tag('span')
    if 'gn-arrow' in el['src']:
      it['style'] = 'color:green;'
      it.string = '▲'
    elif 'rd-arrow' in el['src']:
      it['style'] = 'color:red;'
      it.string = '▼'
    else:
      it['style'] = 'color:orange;'
      it.string = '⬌'
    el.insert_after(it)
    el.decompose()

  for el in story_soup.find_all(re.compile('photo\d+')):
    m = re.search(r'\d+$', el.name)
    n = int(m.group(0)) - 1
    image = story_json['images'][n]
    img_src, caption = get_image(image)
    new_html = utils.add_image(resize_image(img_src), caption)
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in story_soup.find_all(re.compile('video\d+')):
    m = re.search(r'\d+$', el.name)
    n = int(m.group(0)) - 1
    if n < len(story_json['video']):
      video = story_json['video'][n]
      vid_src, vid_type, poster, caption = get_video(video)
      new_html = utils.add_video(vid_src, vid_type, poster, caption)
      el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()
    else:
      logger.warning('video index out of range in ' + url)

  inlines = None
  if story_soup.find(re.compile('inline\d+')):
    # Fetch article html to parse the inlines
    article_html = utils.get_url_html(url)
    if not article_html:
      logger.warning('unable to parse inlines in ' + url)
    article_soup = BeautifulSoup(article_html, 'html.parser')
    inlines = article_soup.find_all(class_=['instagram-media', 'twitter-tweet', 'pull-quote', 'module-iframe-wrapper', 'inline'])

  if inlines:
    for el in story_soup.find_all(re.compile('inline\d+')):
      m = re.search(r'\d+$', el.name)
      n = int(m.group(0)) - 1
      if n > len(inlines):
        logger.warning('inline index out of range ' + url)
        continue
      it = inlines[n]
      new_html = ''
      if 'instagram-media' in it['class']:
        new_html = utils.add_embed(it['data-instgrm-permalink'])

      elif 'twitter-tweet' in it['class']:
        a = a.find_all('a')
        new_html = utils.add_embed(a[-1]['href'])

      elif 'pull-quote' in it['class']:
        author = ''
        a = it.find('cite')
        if a:
          author = a.get_text().strip()
          a.decompose()
        quote = re.sub(r'^"|"$', '', a.get_text().strip())
        new_html = utils.add_pullquote(quote, author)

      elif 'module-iframe-wrapper' in it['class']:
        a = it.find('iframe')
        new_html = utils.add_embed(a['src'])

      elif 'inline-track' in it['class'] or it.name == 'aside':
        pass

      if new_html:
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

  for el in story_soup.find_all(['alsosee', 'offer']):
    if el.parent and el.parent.name == 'p':
      el.parent.decompose()
    else:
      el.decompose()

  item['content_html'] = ''

  # Add lead video or image
  m = re.search(r'<photo\d+>|<video\d+>', story_json['story'][:20])
  if not m:
    if story_json.get('video'):
      vid_src, vid_type, poster, caption = get_video(story_json['video'][0])
      item['content_html'] += utils.add_video(vid_src, vid_type, poster, caption)
    elif story_json.get('images'):
      img_src, caption = get_image(story_json['images'][0])
      item['content_html'] += utils.add_image(resize_image(img_src), caption)

  item['content_html'] += str(story_soup)
  return item

def get_content(url, args, save_debug=False):
  m = re.search(r'\/id\/(\d+)\/', url)
  if not m:
    story_html = utils.get_url_html(url)
    if story_html:
      m = re.search(r'data-id="(\d+)"', story_html)
  if not m:
    logger.warning('unable to parse story id in ' + url)
    return None

  json_url = 'http://now.core.api.espn.com/v1/sports/news/' + m.group(1)
  now_json = utils.get_url_json(json_url)
  if not now_json:
    return None
  if save_debug:
    utils.write_file(now_json, './debug/debug.json')

  return get_story(now_json['headlines'][0], args, save_debug)

def get_feed(args, save_debug=False):
  # API: https://www.espn.com/apis/devcenter/docs/headlines.html
  # All: https://now.core.api.espn.com/v1/sports/news/
  # League: https://now.core.api.espn.com/v1/sports/basketball/nba/news
  # Browns: https://now.core.api.espn.com/v1/sports/football/nfl/teams/5/news
  # Steelers: https://now.core.api.espn.com/v1/sports/football/nfl/teams/23/news
  # Penguins: https://now.core.api.espn.com/v1/sports/hockey/nhl/teams/16/news

  feed_json = utils.get_url_json(args['url'])
  if not feed_json:
    return None
  if save_debug:
    utils.write_file(feed_json, './debug/debug.json')

  n = 0
  items = []
  for story in feed_json['headlines']:
    url = story['links']['web']['href']
    if not 'espn.com' in url:
      if save_debug:
        logger.debug('skipping ' + url)
      continue
    if save_debug:
      logger.debug('getting content for ' + url)
    item = get_story(story, args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args and n == int(args['max']):
          break

  feed = utils.init_jsonfeed(args)
  feed['items'] = items.copy()
  return feed
