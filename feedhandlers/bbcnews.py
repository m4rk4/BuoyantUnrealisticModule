import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils
from feedhandlers import bbc

import logging
logger = logging.getLogger(__name__)

def format_content(model):
  content_html = ''
  for block in model['blocks']:
    if block['type'] == 'text':
      content_html += format_content(block['model'])

    elif block['type'] == 'paragraph':
      content_html += '<p>{}</p>'.format(format_content(block['model']))

    elif block['type'] == 'subheadline':
      content_html += '<h{0}>{1}</h{0}>'.format(block['model']['level'], format_content(block['model']))

    elif block['type'] == 'unorderedList':
      content_html += '<ul>{}</ul>'.format(format_content(block['model']))

    elif block['type'] == 'orderedList':
      content_html += '<ol>{}</ol>'.format(format_content(block['model']))

    elif block['type'] == 'listItem':
      content_html += '<li>{}</li>'.format(format_content(block['model']))

    elif block['type'] == 'fragment':
      start_tag = ''
      end_tag = ''
      for attr in block['model']['attributes']:
        if attr == 'bold':
          start_tag += '<b>'
          end_tag = '</b>' + end_tag
        elif attr == 'italic':
          start_tag += '<i>'
          end_tag = '</i>' + end_tag
        else:
          logger.warning('unhandled attribute {}')
      content_html += start_tag + block['model']['text'] + end_tag

    elif block['type'] == 'urlLink':
      content_html += '<a href="{}">{}</a>'.format(block['model']['locator'], format_content(block['model']))

    elif block['type'] == 'image':
      img_src = utils.image_from_srcset(block['model']['image']['srcSet'], 1000)
      captions = []
      if block['model'].get('caption'):
        captions.append(format_content(block['model']['caption']['model']))
      if block['model']['image'].get('copyright'):
        captions.append(block['model']['image']['copyright'])
      content_html += utils.add_image(img_src, ' | '.join(captions))

    elif block['type'] == 'media':
      if block['model']['media']['__typename'] == 'ElementsMediaPlayer':
        video_src, caption = bbc.get_video_src(block['model']['media']['items'][0]['id'])
        poster = block['model']['media']['items'][0]['holdingImageUrl'].replace('$recipe', '976x549')
        if video_src:
          if block['model'].get('caption'):
            caption = block['model']['caption']
          content_html += utils.add_video(video_src, 'application/x-mpegURL', poster, caption)
        else:
          poster = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(poster))
          content_html += utils.add_image(poster, caption)
      else:
        logger.warning('unhandled media type ' + block['media']['__typename'])

    elif block['type'] == 'socialEmbed':
      if re.search(r'instagram|twitter|youtube', block['model']['source']):
        content_html += utils.add_embed(block['model']['href'])
      else:
        logger.warning('unhandled socialEmbed ' + block['model']['source'])

    elif block['type'] == 'include':
      if block['model']['type'] == 'vj':
        content_html += '<blockquote><b>Embedded content from <a href="https://news.files.bbci.co.uk/{0}">https://news.files.bbci.co.uk/{0}</a></b></blockquote>'.format(block['model']['href'])
      else:
        logger.warning('unhandled include type ' + block['model']['type'])

    else:
      logger.warning('unhandled block type ' + block['type'])

  return content_html

def get_content(url, args, site_json, save_debug=False):
  initial_data = bbc.get_initial_data(url)
  if save_debug:
    utils.write_file(initial_data, './debug/debug.json')

  article_json = None
  for key, val in initial_data['data'].items():
    if key.startswith('article'):
      article_json = val
  if not article_json:
    logger.warning('unable to find article content in ' + url)

  item = {}
  item['id'] = article_json['data']['metadata']['assetId']
  item['url'] = article_json['data']['metadata']['locators']['canonicalUrl']
  item['title'] = article_json['data']['headline']

  dt = datetime.fromtimestamp(article_json['data']['metadata']['firstPublished']/1000).replace(tzinfo=timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = utils.format_display_date(dt)
  dt = datetime.fromtimestamp(article_json['data']['metadata']['lastUpdated']/1000).replace(tzinfo=timezone.utc)
  item['date_modified'] = dt.isoformat()

  item['author'] = {}
  if article_json['data'].get('contributor'):
    item['author']['name'] = re.sub('^By ', '', article_json['data']['contributor']['title'])
  else:
    item['author']['name'] = article_json['data']['metadata']['site']['name']

  item['tags'] = []
  for topic in article_json['data']['topics']:
    item['tags'].append(topic['title'])

  item['_image'] = article_json['data']['metadata']['indexImage']['originalSrc']

  item['summary'] = article_json['data']['metadata']['description']

  item['content_html'] = format_content(article_json['data']['content']['model'])
  return item
