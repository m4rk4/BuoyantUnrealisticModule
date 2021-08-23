import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import utils

import logging
logger = logging.getLogger(__name__)

def resize_image(img_src, width=800):
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
  poster = video['posterImages']['default']['href']
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

  content_html = story_json['story'].replace('\n', '')

  # Add lead video or image
  item['content_html'] = ''
  if not re.search(r'<video\d+>', content_html) and story_json.get('video'):
    vid_src, vid_type, poster, caption = get_video(story_json['video'][0])
    item['content_html'] += utils.add_video(vid_src, vid_type, poster, caption)
  elif not re.search(r'<photo\d+>', content_html) and story_json.get('images'):
    img_src, caption = get_image(story_json['images'][0])
    item['content_html'] += utils.add_image(resize_image(img_src), caption)

  def replace_photo(matchobj):
    nonlocal story_json
    n = int(matchobj.group(1)) - 1
    image = story_json['images'][n]
    img_src, caption = get_image(image)
    return utils.add_image(resize_image(img_src), caption)
  content_html = re.sub(r'<p><photo(\d+)><\/p>', replace_photo, content_html)
  content_html = re.sub(r'<photo(\d+)>', replace_photo, content_html)

  def replace_video(matchobj):
    nonlocal story_json
    n = int(matchobj.group(1)) - 1
    video = story_json['video'][n]
    vid_src, vid_type, poster, caption = get_video(video)
    return utils.add_video(vid_src, vid_type, poster, caption)
  content_html = re.sub(r'<p><video(\d+)>\s?<\/video\d+><\/p>', replace_video, content_html)

  if re.search(r'<inline\d>', content_html):
    story_html = utils.get_url_html(url)
    if story_html:
      story_soup = BeautifulSoup(story_html, 'html.parser')
      inlines = story_soup.find_all(class_=['instagram-media', 'twitter-tweet', 'pull-quote', 'module-iframe-wrapper', 'inline-track'])

      def replace_inline(matchobj):
        nonlocal inlines
        nonlocal url
        n = int(matchobj.group(1)) - 1
        if n < len(inlines):
          el = inlines[n]
          if 'instagram-media' in el['class']:
            return utils.add_instagram(el['data-instgrm-permalink'])
          elif 'twitter-tweet' in el['class']:
            it = el.find_all('a')
            tweet_url = it[-1]['href']
            tweet = utils.add_twitter(tweet_url)
            if tweet:
              return tweet
            else:
              logger.warning('unable to add tweet {} in {}'.format(tweet_url, url))
          elif 'pull-quote' in el['class']:
            author = ''
            it = el.find('cite')
            if it:
              author = it.get_text().strip()
              it.decompose()
            quote = re.sub(r'^"|"$', '', el.get_text().strip())
            return utils.add_pullquote(quote, author)
          elif 'inline-track' in el['class']:
            # Skip
            return ''
          elif 'module-iframe-wrapper' in el['class']:
            it = el.find('iframe')
            logger.warning('skipping iframe ' + it['src'])
            return ''
        logger.warning('unhandled inline in ' + url)
        return matchobj.group(0)
      content_html = re.sub(r'<p><inline(\d+)><\/p>', replace_inline, content_html)
      content_html = re.sub(r'<inline(\d+)>', replace_inline, content_html)

  content_html = re.sub(r'(<p>)?<alsosee><\/p>', '', content_html)

  item['content_html'] += content_html
  return item

def get_content(url, args, save_debug=False):
  story_html = ''
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
