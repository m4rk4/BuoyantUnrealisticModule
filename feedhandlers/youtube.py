import json, re
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def search(query, save_debug=False):
  search_html = utils.get_url_html(
    'https://www.youtube.com/results?search_query=' + quote_plus(query))
  if search_html:
    m = re.search(r'var ytInitialData = (.*});<\/script>', search_html)
    if m:
      search_json = json.loads(m.group(1))
      if save_debug:
        utils.write_file(search_json, './debug/search.json')
      contents = search_json['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']
      for content in contents:
        if content.get('videoRenderer'):
          return content['videoRenderer']['videoId']
  logger.warning('unable to get Youtube search results for query "{}"'.format(query))
  return ''

def get_content(url, args, save_debug=False):
  yt_video_id, yt_list_id = utils.get_youtube_id(url)
  if not yt_video_id:
    return None

  yt_embed_url = 'https://www.youtube-nocookie.com/embed/{}'.format(yt_video_id)
  yt_watch_url = 'https://www.youtube.com/watch?v={}'.format(yt_video_id)

  yt_html = utils.get_url_html(yt_watch_url)
  if not yt_html:
    return None
  if save_debug:
    utils.write_file(yt_html, './debug/youtube.html')

  m = re.search(r'ytInitialPlayerResponse = (.+?);(<\/script>|var)', yt_html)
  if not m:
    logger.warning('unable to extract yt info from ' + url)
    return None

  if False:
    utils.write_file(m.group(1), './debug/debug.txt')

  yt_json = json.loads(m.group(1))
  if save_debug:
    utils.write_file(yt_json, './debug/youtube.json')

  item = {}
  item['id'] = yt_video_id
  item['url'] = yt_watch_url

  if yt_json['playabilityStatus']['status'] == 'ERROR' or yt_json['playabilityStatus']['status'] == 'LOGIN_REQUIRED':
    if yt_json['playabilityStatus'].get('reason'):
      caption = yt_json['playabilityStatus']['reason']
      if yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer'].get('subreason'):
        if yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason'].get('simpleText'):
          caption += '. ' + yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason']['simpleText']
        elif yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason'].get('runs'):
          caption += '. ' + yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason']['runs'][0]['text']
    elif yt_json['playabilityStatus'].get('messages'):
      caption = ' '.join(yt_json['playabilityStatus']['messages'])
    else:
      caption = ''
    item['title'] = caption

    if yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer'].get('thumbnail'):
      overlay = yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['thumbnail']['thumbnails'][0]['url']
      if overlay.startswith('//'):
        overlay = 'https:' + overlay
      poster = '{}/image?width=1280&height=720&overlay={}'.format(config.server, quote_plus(overlay))
    else:
      poster = '{}/image?width=1280&height=720&overlay=video'.format(config.server)

    item['content_html'] = utils.add_image(poster, caption, link=yt_embed_url)
    return item

  item['title'] = yt_json['videoDetails']['title']

  item['author'] = {}
  item['author']['name'] = yt_json['videoDetails']['author']

  if yt_json['videoDetails'].get('keywords'):
    item['tags'] = yt_json['videoDetails']['keywords'].copy()

  images = yt_json['videoDetails']['thumbnail']['thumbnails'] + yt_json['microformat']['playerMicroformatRenderer']['thumbnail']['thumbnails']
  image = utils.closest_dict(images, 'height', 1080)
  if image['height'] < 360:
    item['_image'] = image['url'].split('?')[0]
  else:
    item['_image'] = image['url']

  item['summary'] = yt_json['videoDetails']['shortDescription']

  if yt_json['playabilityStatus']['status'] == 'OK':
    caption = '{} | <a href="{}">Watch on YouTube</a>'.format(item['title'], item['url'])
    if yt_list_id:
      caption += ' | <a href="{}&list={}">View playlist</a>'.format(yt_watch_url, yt_list_id)
    poster = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(item['_image']))
    item['content_html'] = utils.add_image(poster, caption, link=yt_embed_url)
  else:
    error_reason = 'Error'
    if yt_json['playabilityStatus'].get('errorScreen'):
      overlay = yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['thumbnail']['thumbnails'][0]['url']
      if overlay.startswith('//'):
        overlay = 'https:' + overlay
      poster = '{}/image?url={}&overlay={}'.format(config.server, quote_plus(item['_image']), quote_plus(overlay))
      error_reason = yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['reason']['simpleText']
    else:
      poster = '{}/image?url={}'.format(config.server, quote_plus(item['_image']))
    if not error_reason and yt_json['playabilityStatus'].get('reason'):
      error_reason = yt_json['playabilityStatus']['reason']
    caption = '{} | {} | <a href="{}">Watch on YouTube</a>'.format(error_reason, item['title'], yt_embed_url)
    if yt_list_id:
      caption += ' | <a href="{}&list={}">View playlist</a>'.format(yt_watch_url, yt_list_id)
    item['content_html'] = utils.add_image(poster, caption, link=yt_embed_url)

  if args and 'embed' in args:
    return item

  summary_html = yt_json['videoDetails']['shortDescription'].replace('\n', ' <br /> ')
  def replace_link(matchobj):
    return '<a href="{0}">{0}</a>'.format(matchobj.group(0))
  summary_html = re.sub('https?:\/\/[^\s]+', replace_link, summary_html)
  item['content_html'] += '<p>{}</p>'.format(summary_html)
  return item

def get_feed(args, save_debug=False):
  n = 0
  items = []
  feed = rss.get_feed(args, save_debug)
  for feed_item in feed['items']:
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
