import json, operator, re
from datetime import datetime, timezone
from urllib.parse import urlsplit, unquote

from feedhandlers import rss, twitter
import utils

import logging
logger = logging.getLogger(__name__)

graphql_json = None

def medium_image_src(image_id, width=800):
  return 'https://miro.medium.com/max/{}/{}'.format(width, image_id)

def get_content(url, args, save_debug=False):
  clean_url = utils.clean_url(url)
  article_html = utils.get_url_html(clean_url)
  if not article_html:
    return None
  if save_debug:
    utils.write_file(article_html, './debug/debug.html')

  m = re.search(r'<script>window\.__APOLLO_STATE__ = ({.+?})<\/script>', article_html)
  if not m:
    logger.warning('No __APOLLO_STATE__ data found in ' + url)
    return None

  try:
    article_json = json.loads(m.group(1))
  except:
    logger.warning('Error loading __APOLLO_STATE__ json data from ' + url)
    if save_debug:
      utils.write_file(m.group(1), './debug/debug.txt')
    return None
  if save_debug:
    utils.write_file(article_json, './debug/debug.json')

  m = re.search(r'-([a-f0-9]+)$', clean_url)
  if m:
    post_id = m.group(1)
  else:
    for key in article_json['ROOT_QUERY']:
      if key.startswith('postResult'):
        m = re.search(r'\"id\":\"([a-f0-9]+)\"', key)
        if m:
          post_id = m.group(1)

  post = article_json['Post:' + post_id]

  item = {}
  item['id'] = post_id
  item['url'] = clean_url
  item['title'] = post['title']

  dt = datetime.fromtimestamp(post['firstPublishedAt']/1000).replace(tzinfo=timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromtimestamp(post['updatedAt']/1000).replace(tzinfo=timezone.utc)
  item['date_modified'] = dt.isoformat()

  # Check age
  if args.get('age'):
    if not utils.check_age(item, args):
      return None

  if post.get('creator'):
    item['author'] = {}
    item['author']['name'] = article_json[post['creator']['__ref']]['name']

  tags = []
  if post.get('tags'):
    for tag in post['tags']:
      tags.append(article_json[tag['__ref']]['displayTitle'])
  if post.get('topics'):
    for tag in post['topics']:
      tags.append(tag['name'])
  if tags:
    item['tags'] = list(set(tags))

  if post.get('previewImage'):
    item['_image'] = medium_image_src(article_json[post['previewImage']['__ref']]['id'])

  if post.get('previewContent'):
    item['summary'] = post['previewContent']['subtitle']

  is_list = ''
  content_html = ''
  for key in post.keys():
    if key.startswith('content({\"postMeteringOptions'):
      break
  for p in post[key]['bodyModel']['paragraphs']:
    paragraph = article_json[p['__ref']]
    paragraph_type = paragraph['type'].lower()

    # The first 2 paragraphs are often the title and subtext
    if (p['__ref'].endswith('_0') and paragraph_type == 'h3') or (p['__ref'].endswith('_1') and paragraph_type == 'h4'):
      continue

    if is_list and not (paragraph_type == 'oli' or paragraph_type == 'uli'):
      start_tag = '</{}>'.format(is_list)
      is_list = ''
    else:
      start_tag = ''
  
    if paragraph_type == 'p' or paragraph_type == 'h1' or paragraph_type == 'h2' or paragraph_type == 'h3' or paragraph_type == 'h4' or paragraph_type == 'pre':
      start_tag += '<{}>'.format(paragraph_type)
      end_tag = '</{}>'.format(paragraph_type)
      paragraph_text = paragraph['text']

    elif paragraph_type == 'img':
      image = article_json[paragraph['metadata']['__ref']]
      start_tag += '<div class="image"><figure><img width="100%" src="{}" /><figcaption><small>'.format(medium_image_src(image['id']))
      end_tag = '</small></figcaption></figure></div>'
      paragraph_text = paragraph['text']

    elif paragraph_type == 'bq' or paragraph_type == 'pq':
      start_tag += '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;">'
      end_tag = '</blockquote>'
      paragraph_text = paragraph['text']

    elif paragraph_type == 'oli' or paragraph_type == 'uli':
      if is_list:
        start_tag += '<li>'
        end_tag = '</li>'
      else:
        if paragraph_type == 'oli':
          is_list = 'ol'
        else:
          is_list = 'ul'
        start_tag += '<{}><li>'.format(is_list)
        end_tag = '</li>'
      paragraph_text = paragraph['text']

    elif paragraph_type == 'iframe':
      media_resource = article_json[paragraph['iframe']['mediaResource']['__ref']]
      iframe_src = media_resource['iframeSrc']
      if iframe_src:
        if 'youtube' in iframe_src:
          split_url = urlsplit(iframe_src)
          m = re.search(r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})', unquote(split_url.query))
          if m:
            start_tag += utils.add_video('https://www.youtube-nocookie.com/embed/' + m.group(1), 'youtube')
            end_tag = ''
            paragraph_text = ''
            iframe_src = ''

        elif 'twitter' in iframe_src:
          split_url = urlsplit(iframe_src)
          m = re.search(r'https:\/\/twitter\.com\/[^\/]+\/status\/\d+', unquote(split_url.query))
          if m:
            tweet = twitter.get_content(m.group(0), None, save_debug)
            if tweet:
              start_tag += tweet['content_html']
              end_tag = ''
              paragraph_text = ''
              iframe_src = ''
            else:
              logger.warning('unable to get tweet {} in {}'.format(m.group(0), url))

        else:
          logger.warning('unhandled iframe_src {} in {}'.format(iframe_src, url))

      else:
        split_url = urlsplit(url)
        iframe_src = '{}://{}/media/{}'.format(split_url.scheme, split_url.netloc,  media_resource['id'])
        iframe_html = utils.get_url_html(iframe_src)
        if iframe_html:
          if save_debug:
            utils.write_file(iframe_html, './debug/debug.html')
          m = re.search(r'src="https:\/\/gist\.github\.com\/([^\/]+)\/([^\.]+)\.js"', iframe_html)
          if m:
            iframe_html = utils.get_url_html('https://gist.githubusercontent.com/{}/{}/raw'.format(m.group(1), m.group(2)))
            if iframe_html:
              start_tag = '<pre style="margin-left:2em;">{}</pre>'.format(iframe_html)
              end_tag = ''
              paragraph_text = ''
              iframe_src = ''
          else:
            logger.warning('unhandled Medium media iframe in ' + url)
            iframe_src = ''

      if iframe_src:
        width = 640
        if 'iframeWidth' in paragraph['iframe']['mediaResource'] and paragraph['iframe']['mediaResource']['iframeWidth'] > 0:
          width = paragraph['iframe']['mediaResource']['iframeWidth']

        height = 480
        if 'iframeHeight' in paragraph['iframe']['mediaResource'] and paragraph['iframe']['mediaResource']['iframeHeight'] > 0:
          height = paragraph['iframe']['mediaResource']['iframeHeight']

        title = ''
        if paragraph['iframe']['mediaResource'].get('title'):
          title = " title={}".format(paragraph['iframe']['mediaResource']['title'])
        start_tag += '<iframe src="{}" width="{}" height="{}"{} frameborder="0" scrolling="auto">'.format(iframe_src, width, height, title)
        end_tag = '</iframe>'
        paragraph_text = ''

    elif paragraph_type == 'mixtape_embed':
      mixtape = paragraph['mixtapeMetadata']
      start_tag += '<table style="width:80%; height:5em; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px;"><tr><td><a style="text-decoration:none;" href="{}"><small>'.format(mixtape['href'])
      end_tag = '</small></a></td><td style="padding:0;"><img style="height:5em; display:block; border-top-right-radius:10px; border-bottom-right-radius:10px;" src="{}" /></td></tr></table>'.format(medium_image_src(mixtape['thumbnailImageId'], 200))

      paragraph_text = paragraph['text']

    else:
      logger.warning('unhandled paragraph type {} in {}'.format(paragraph_type, url))
      continue

    if paragraph.get('markups'):
      starts = list(map(operator.itemgetter('start'), paragraph['markups']))
      ends = list(map(operator.itemgetter('end'), paragraph['markups']))
      markup_text = paragraph_text[0:min(starts)]
      for i in range(min(starts), max(ends)+1):
        for n in range(len(starts)):
          if starts[n] == i:
            markup_type = paragraph['markups'][n]['type'].lower()
            if markup_type == 'a':
              markup_text += '<a href="{}">'.format(paragraph['markups'][n]['href'])
            elif markup_type == 'code' or markup_type == 'em' or markup_type == 'strong':
              markup_text += '<{}>'.format(markup_type)
            else:
              logger.warning('unhandled markup type {} in {}'.format(markup_type, url))
            starts[n] = -1

        for n in reversed(range(len(ends))):
          if ends[n] == i:
            markup_type = paragraph['markups'][n]['type'].lower()
            if markup_type == 'a' or markup_type == 'code' or markup_type == 'em' or markup_type == 'strong':
              markup_text += '</{}>'.format(markup_type)
            else:
              logger.warning('unhandled markup type {} in {}'.format(markup_type, url))
            ends[n] = -1

        if i < len(paragraph_text):
          markup_text += paragraph_text[i]

      markup_text += paragraph_text[i+1:]
    else:
      markup_text = paragraph_text
    markup_text = markup_text.replace('\n', '<br />')

    content_html += start_tag + markup_text + end_tag

  # Close an open list tag if it was the last element
  if is_list:
    content_html += '</{}>'.format(is_list)

  # Remove the title
  #content_html = re.sub(r'<h3.*>{}<.*\/h3>'.format(item['title']), '', content_html)

  item['content_html'] = content_html
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)