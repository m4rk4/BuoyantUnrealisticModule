import html, json, operator, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_image(image, caption='', width=1000):
    img_src = 'https://miro.medium.com/max/{}/{}'.format(width, image['id'])
    if image.get('originalWidth'):
        if image['originalWidth'] < width:
            img_src = '{}/image?url={}&width={}'.format(config.server, quote_plus(img_src), width)
    return utils.add_image(img_src, caption)


def get_apollo_state_content(url):
    page_html = utils.get_url_html(url, user_agent='googlecache')
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'__APOLLO_STATE__'))
    if not el:
        return None
    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    apollo_state = json.loads(el.string[i:j])
    post_id = 'Post:' + urlsplit(url).path.split('-')[-1]
    if not apollo_state.get(post_id):
        return None
    utils.write_file(apollo_state, './debug/apollo.json')
    post_json = apollo_state[post_id]
    content_json = None
    for key, val in post_json.items():
        if key.startswith('content'):
            content_json = val
            break
    if not content_json:
        return None

    def sub_refs(matchobj):
        nonlocal apollo_state
        ref = json.dumps(apollo_state[matchobj.group(1)])[1:-1]
        return re.sub(r'"__ref": "([^"]+)"', sub_refs, ref)
    paragraphs = re.sub(r'"__ref": "([^"]+)"', sub_refs, json.dumps(content_json['bodyModel']['paragraphs']))
    utils.write_file(paragraphs, './debug/test.txt')
    content_json['bodyModel']['paragraphs'] = json.loads(paragraphs)
    return content_json


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    post_id = split_url.path.split('-')[-1]
    graphql_url = '{}://{}/_/graphql'.format(split_url.scheme, split_url.netloc)
    data = [
        {
            "operationName": "PostPageQuery",
            "variables": {
                "postId": post_id,
                "postMeteringOptions": {
                    "referrer": "https://" + split_url.netloc + '/'
                },
                "includeShouldFollowPost": False
            },
            "query": "query PostPageQuery($postId: ID!, $postMeteringOptions: PostMeteringOptions, $includeShouldFollowPost: Boolean!) {\n  postResult(id: $postId) {\n    __typename\n    ...PostResultError_postResult\n    ... on Post {\n      id\n      collection {\n        id\n        googleAnalyticsId\n        ...FloatingPublicationBio_collection\n        ...MoreFromAuthorAndMaybePub_collection\n        ...PostPublishersInfoSection_collection\n        ...PublicationNav_collection\n        __typename\n      }\n      content(postMeteringOptions: $postMeteringOptions) {\n        isLockedPreviewOnly\n        __typename\n      }\n      creator {\n        id\n        ...MastodonVerificationLink_user\n        ...SuspendedBannerLoader_user\n        ...MoreFromAuthorAndMaybePub_user\n        ...PostPublishersInfoSection_user\n        __typename\n      }\n      inResponseToEntityType\n      isLocked\n      ...Wall_post\n      ...InteractivePostBody_post\n      ...WithResponsesSidebar_post\n      ...PostCanonicalizer_post\n      ...PostFooterActionsBar_post\n      ...PostReadTracker_post\n      ...PostMetadata_post\n      ...SuspendedBannerLoader_post\n      ...PostFooterInfo_post\n      ...PostBodyInserts_post\n      ...PostNoteMissingToast_post\n      ...usePostTracking_post\n      ...InResponseToEntityPreview_post\n      ...PostPublishedDialog_prerequisite_post\n      ...PostResponses_post\n      __typename\n    }\n  }\n}\n\nfragment UnavailableForLegalReasonsScreen_unavailableForLegalReasons on UnavailableForLegalReasons {\n  lumenId\n  __typename\n}\n\nfragment WithheldInCountryScreen_withheldInCountry on WithheldInCountry {\n  lumenId\n  __typename\n}\n\nfragment collectionUrl_collection on Collection {\n  id\n  domain\n  slug\n  __typename\n}\n\nfragment CollectionAvatar_collection on Collection {\n  name\n  avatar {\n    id\n    __typename\n  }\n  ...collectionUrl_collection\n  __typename\n  id\n}\n\nfragment PublisherDescription_publisher on Publisher {\n  __typename\n  id\n  ... on Collection {\n    description\n    __typename\n    id\n  }\n  ... on User {\n    bio\n    __typename\n    id\n  }\n}\n\nfragment SignInOptions_collection on Collection {\n  id\n  name\n  __typename\n}\n\nfragment SignUpOptions_collection on Collection {\n  id\n  name\n  __typename\n}\n\nfragment SusiContainer_collection on Collection {\n  name\n  ...SignInOptions_collection\n  ...SignUpOptions_collection\n  __typename\n  id\n}\n\nfragment SusiClickable_collection on Collection {\n  ...SusiContainer_collection\n  __typename\n  id\n}\n\nfragment CollectionFollowButton_collection on Collection {\n  __typename\n  id\n  name\n  slug\n  ...collectionUrl_collection\n  ...SusiClickable_collection\n}\n\nfragment useIsVerifiedBookAuthor_user on User {\n  verifications {\n    isBookAuthor\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment userUrl_user on User {\n  __typename\n  id\n  customDomainState {\n    live {\n      domain\n      __typename\n    }\n    __typename\n  }\n  hasSubdomain\n  username\n}\n\nfragment PublisherLink_user on User {\n  ...userUrl_user\n  __typename\n  id\n}\n\nfragment PublisherLink_collection on Collection {\n  ...collectionUrl_collection\n  __typename\n  id\n}\n\nfragment PublisherName_publisher on Publisher {\n  id\n  name\n  __typename\n}\n\nfragment PublisherFollowersCount_publisher on Publisher {\n  id\n  __typename\n  id\n  ... on Collection {\n    slug\n    subscriberCount\n    ...collectionUrl_collection\n    __typename\n    id\n  }\n  ... on User {\n    socialStats {\n      followerCount\n      __typename\n    }\n    username\n    ...userUrl_user\n    __typename\n    id\n  }\n}\n\nfragment UserAvatar_user on User {\n  __typename\n  id\n  imageId\n  membership {\n    tier\n    __typename\n    id\n  }\n  name\n  username\n  ...userUrl_user\n}\n\nfragment PublisherAvatar_publisher on Publisher {\n  __typename\n  ... on Collection {\n    id\n    ...CollectionAvatar_collection\n    __typename\n  }\n  ... on User {\n    id\n    ...UserAvatar_user\n    __typename\n  }\n}\n\nfragment UserFollowButtonSignedIn_user on User {\n  id\n  name\n  __typename\n}\n\nfragment SignInOptions_user on User {\n  id\n  name\n  __typename\n}\n\nfragment SignUpOptions_user on User {\n  id\n  name\n  __typename\n}\n\nfragment SusiContainer_user on User {\n  ...SignInOptions_user\n  ...SignUpOptions_user\n  __typename\n  id\n}\n\nfragment SusiClickable_user on User {\n  ...SusiContainer_user\n  __typename\n  id\n}\n\nfragment UserFollowButtonSignedOut_user on User {\n  id\n  ...SusiClickable_user\n  __typename\n}\n\nfragment UserFollowButton_user on User {\n  ...UserFollowButtonSignedIn_user\n  ...UserFollowButtonSignedOut_user\n  __typename\n  id\n}\n\nfragment PublisherFollowButton_publisher on Publisher {\n  __typename\n  ... on Collection {\n    ...CollectionFollowButton_collection\n    __typename\n    id\n  }\n  ... on User {\n    ...UserFollowButton_user\n    __typename\n    id\n  }\n}\n\nfragment usePostUrl_post on Post {\n  id\n  creator {\n    ...userUrl_user\n    __typename\n    id\n  }\n  collection {\n    id\n    domain\n    slug\n    __typename\n  }\n  isSeries\n  mediumUrl\n  sequence {\n    slug\n    __typename\n  }\n  uniqueSlug\n  __typename\n}\n\nfragment CollectionLastPostDate_collection on Collection {\n  __typename\n  ... on Collection {\n    latestPostsConnection(paging: {limit: 1}) {\n      posts {\n        id\n        firstPublishedAt\n        ...usePostUrl_post\n        __typename\n      }\n      __typename\n    }\n    __typename\n    id\n  }\n  id\n}\n\nfragment PublisherFollowingCount_publisher on Publisher {\n  __typename\n  id\n  ... on User {\n    socialStats {\n      followingCount\n      collectionFollowingCount\n      __typename\n    }\n    username\n    __typename\n    id\n  }\n}\n\nfragment PublisherFollowingCountOrLastPostDate_publisher on Publisher {\n  __typename\n  ... on Collection {\n    ...CollectionLastPostDate_collection\n    __typename\n    id\n  }\n  ...PublisherFollowingCount_publisher\n}\n\nfragment PostPublisherInfo_publisher on Publisher {\n  __typename\n  id\n  name\n  ... on User {\n    ...useIsVerifiedBookAuthor_user\n    ...PublisherLink_user\n    __typename\n    id\n  }\n  ... on Collection {\n    ...PublisherLink_collection\n    __typename\n    id\n  }\n  ...PublisherName_publisher\n  ...PublisherFollowersCount_publisher\n  ...PublisherDescription_publisher\n  ...PublisherAvatar_publisher\n  ...PublisherFollowButton_publisher\n  ...PublisherFollowingCountOrLastPostDate_publisher\n}\n\nfragment PublicationNavColorBar_collection on Collection {\n  id\n  avatar {\n    id\n    __typename\n  }\n  customStyleSheet {\n    id\n    global {\n      colorPalette {\n        background {\n          rgb\n          __typename\n        }\n        primary {\n          rgb\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  isAuroraVisible\n  tintColor\n  __typename\n}\n\nfragment PublicationNavMobileItems_collection on Collection {\n  id\n  ...CollectionFollowButton_collection\n  __typename\n}\n\nfragment SusiContainer_post on Post {\n  id\n  __typename\n}\n\nfragment SusiClickable_post on Post {\n  id\n  mediumUrl\n  ...SusiContainer_post\n  __typename\n}\n\nfragment RegWall_post on Post {\n  id\n  lockedSource\n  ...SusiClickable_post\n  __typename\n}\n\nfragment EntityPaywall_post on Post {\n  id\n  creator {\n    name\n    __typename\n    id\n  }\n  __typename\n}\n\nfragment AspirationalPaywall_post on Post {\n  ...EntityPaywall_post\n  __typename\n  id\n}\n\nfragment ProgrammingPaywall_post on Post {\n  ...EntityPaywall_post\n  __typename\n  id\n}\n\nfragment Paywall_post on Post {\n  id\n  creator {\n    id\n    name\n    imageId\n    __typename\n  }\n  primaryTopic {\n    slug\n    __typename\n    id\n  }\n  topics {\n    slug\n    __typename\n  }\n  ...AspirationalPaywall_post\n  ...ProgrammingPaywall_post\n  __typename\n}\n\nfragment DropCap_image on ImageMetadata {\n  id\n  originalHeight\n  originalWidth\n  __typename\n}\n\nfragment MarkupNode_data_dropCapImage on ImageMetadata {\n  ...DropCap_image\n  __typename\n  id\n}\n\nfragment Markups_markup on Markup {\n  type\n  start\n  end\n  href\n  anchorType\n  userId\n  linkMetadata {\n    httpStatus\n    __typename\n  }\n  __typename\n}\n\nfragment Markups_paragraph on Paragraph {\n  name\n  text\n  hasDropCap\n  dropCapImage {\n    ...MarkupNode_data_dropCapImage\n    __typename\n    id\n  }\n  markups {\n    ...Markups_markup\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment ParagraphRefsMapContext_paragraph on Paragraph {\n  id\n  name\n  text\n  __typename\n}\n\nfragment PostViewNoteCard_paragraph on Paragraph {\n  name\n  __typename\n  id\n}\n\nfragment PostAnnotationsMarker_paragraph on Paragraph {\n  ...PostViewNoteCard_paragraph\n  __typename\n  id\n}\n\nfragment ImageParagraph_paragraph on Paragraph {\n  href\n  layout\n  metadata {\n    id\n    originalHeight\n    originalWidth\n    focusPercentX\n    focusPercentY\n    alt\n    __typename\n  }\n  ...Markups_paragraph\n  ...ParagraphRefsMapContext_paragraph\n  ...PostAnnotationsMarker_paragraph\n  __typename\n  id\n}\n\nfragment TextParagraph_paragraph on Paragraph {\n  type\n  hasDropCap\n  codeBlockMetadata {\n    mode\n    lang\n    __typename\n  }\n  ...Markups_paragraph\n  ...ParagraphRefsMapContext_paragraph\n  __typename\n  id\n}\n\nfragment IframeParagraph_paragraph on Paragraph {\n  type\n  iframe {\n    mediaResource {\n      id\n      iframeSrc\n      iframeHeight\n      iframeWidth\n      title\n      __typename\n    }\n    __typename\n  }\n  layout\n  ...Markups_paragraph\n  __typename\n  id\n}\n\nfragment GenericMixtapeParagraph_paragraph on Paragraph {\n  text\n  mixtapeMetadata {\n    href\n    thumbnailImageId\n    __typename\n  }\n  markups {\n    start\n    end\n    type\n    href\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment MixtapeParagraph_paragraph on Paragraph {\n  type\n  mixtapeMetadata {\n    href\n    mediaResource {\n      mediumCatalog {\n        id\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  ...GenericMixtapeParagraph_paragraph\n  __typename\n  id\n}\n\nfragment CodeBlockParagraph_paragraph on Paragraph {\n  codeBlockMetadata {\n    lang\n    mode\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment PostBodyParagraph_paragraph on Paragraph {\n  name\n  type\n  ...ImageParagraph_paragraph\n  ...TextParagraph_paragraph\n  ...IframeParagraph_paragraph\n  ...MixtapeParagraph_paragraph\n  ...CodeBlockParagraph_paragraph\n  __typename\n  id\n}\n\nfragment PostBodySection_paragraph on Paragraph {\n  name\n  ...PostBodyParagraph_paragraph\n  __typename\n  id\n}\n\nfragment normalizedBodyModel_richText_paragraphs_markups on Markup {\n  type\n  __typename\n}\n\nfragment getParagraphHighlights_paragraph on Paragraph {\n  name\n  __typename\n  id\n}\n\nfragment getParagraphPrivateNotes_paragraph on Paragraph {\n  name\n  __typename\n  id\n}\n\nfragment normalizedBodyModel_richText_paragraphs on Paragraph {\n  markups {\n    ...normalizedBodyModel_richText_paragraphs_markups\n    __typename\n  }\n  codeBlockMetadata {\n    lang\n    mode\n    __typename\n  }\n  ...getParagraphHighlights_paragraph\n  ...getParagraphPrivateNotes_paragraph\n  __typename\n  id\n}\n\nfragment getSectionEndIndex_section on Section {\n  startIndex\n  __typename\n}\n\nfragment getParagraphStyles_richText on RichText {\n  paragraphs {\n    text\n    type\n    __typename\n  }\n  sections {\n    ...getSectionEndIndex_section\n    __typename\n  }\n  __typename\n}\n\nfragment paragraphExtendsImageGrid_paragraph on Paragraph {\n  layout\n  type\n  __typename\n  id\n}\n\nfragment getSeriesParagraphTopSpacings_richText on RichText {\n  paragraphs {\n    id\n    __typename\n  }\n  sections {\n    ...getSectionEndIndex_section\n    __typename\n  }\n  __typename\n}\n\nfragment getPostParagraphTopSpacings_richText on RichText {\n  paragraphs {\n    type\n    layout\n    text\n    codeBlockMetadata {\n      lang\n      mode\n      __typename\n    }\n    __typename\n  }\n  sections {\n    ...getSectionEndIndex_section\n    __typename\n  }\n  __typename\n}\n\nfragment getParagraphSpaces_richText on RichText {\n  paragraphs {\n    layout\n    metadata {\n      originalHeight\n      originalWidth\n      id\n      __typename\n    }\n    type\n    ...paragraphExtendsImageGrid_paragraph\n    __typename\n  }\n  ...getSeriesParagraphTopSpacings_richText\n  ...getPostParagraphTopSpacings_richText\n  __typename\n}\n\nfragment normalizedBodyModel_richText on RichText {\n  paragraphs {\n    ...normalizedBodyModel_richText_paragraphs\n    __typename\n  }\n  sections {\n    startIndex\n    ...getSectionEndIndex_section\n    __typename\n  }\n  ...getParagraphStyles_richText\n  ...getParagraphSpaces_richText\n  __typename\n}\n\nfragment PostBody_bodyModel on RichText {\n  sections {\n    name\n    startIndex\n    textLayout\n    imageLayout\n    backgroundImage {\n      id\n      originalHeight\n      originalWidth\n      __typename\n    }\n    videoLayout\n    backgroundVideo {\n      videoId\n      originalHeight\n      originalWidth\n      previewImageId\n      __typename\n    }\n    __typename\n  }\n  paragraphs {\n    id\n    ...PostBodySection_paragraph\n    __typename\n  }\n  ...normalizedBodyModel_richText\n  __typename\n}\n\nfragment HighlighSegmentContext_paragraph on Paragraph {\n  ...ParagraphRefsMapContext_paragraph\n  __typename\n  id\n}\n\nfragment NormalizeHighlights_paragraph on Paragraph {\n  name\n  text\n  __typename\n  id\n}\n\nfragment HighlightMenuOption_post on Post {\n  id\n  latestPublishedVersion\n  __typename\n}\n\nfragment RespondMenuOption_post on Post {\n  id\n  latestPublishedVersion\n  __typename\n}\n\nfragment ShareMenuOption_post on Post {\n  id\n  latestPublishedVersion\n  creator {\n    name\n    __typename\n    id\n  }\n  __typename\n}\n\nfragment SelectionMenuPopover_post on Post {\n  isPublished\n  allowResponses\n  isLimitedState\n  responsesLocked\n  visibility\n  isLocked\n  creator {\n    allowNotes\n    __typename\n    id\n  }\n  ...HighlightMenuOption_post\n  ...RespondMenuOption_post\n  ...ShareMenuOption_post\n  __typename\n  id\n}\n\nfragment SelectionMenu_post on Post {\n  isPublished\n  creator {\n    allowNotes\n    __typename\n    id\n  }\n  ...SelectionMenuPopover_post\n  __typename\n  id\n}\n\nfragment PostNewNoteCard_post on Post {\n  id\n  latestPublishedVersion\n  __typename\n}\n\nfragment ActiveSelectionContext_post on Post {\n  id\n  ...SelectionMenu_post\n  ...PostNewNoteCard_post\n  __typename\n}\n\nfragment ReportUserMenuItem_post on Post {\n  __typename\n  id\n  creator {\n    id\n    __typename\n  }\n  ...SusiClickable_post\n}\n\nfragment useHideResponseParent_post on Post {\n  __typename\n  id\n  creator {\n    id\n    __typename\n  }\n  collection {\n    id\n    viewerEdge {\n      id\n      isEditor\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment HideResponseMenuItemParent_post on Post {\n  id\n  ...useHideResponseParent_post\n  __typename\n}\n\nfragment BlockUserMenuItem_post on Post {\n  __typename\n  id\n  creator {\n    id\n    __typename\n  }\n}\n\nfragment UndoClapsMenuItem_post on Post {\n  id\n  clapCount\n  __typename\n}\n\nfragment DeleteResponseMenuItem_post on Post {\n  creator {\n    id\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment useReportStory_post on Post {\n  id\n  creator {\n    id\n    __typename\n  }\n  __typename\n}\n\nfragment ReportResponseDialog_post on Post {\n  __typename\n  id\n  creator {\n    id\n    __typename\n  }\n  ...useHideResponseParent_post\n  ...useReportStory_post\n}\n\nfragment ResponsePopoverMenu_post on Post {\n  id\n  responseDistribution\n  ...ReportUserMenuItem_post\n  ...HideResponseMenuItemParent_post\n  ...BlockUserMenuItem_post\n  ...UndoClapsMenuItem_post\n  ...DeleteResponseMenuItem_post\n  ...ReportResponseDialog_post\n  __typename\n}\n\nfragment ResponseHeaderParentEntity_post on Post {\n  __typename\n  creator {\n    id\n    __typename\n  }\n  ...ResponsePopoverMenu_post\n  id\n}\n\nfragment SimpleResponseParentEntity_post on Post {\n  ...ResponseHeaderParentEntity_post\n  __typename\n  id\n}\n\nfragment ReadOrEditSimpleResponseParentEntity_post on Post {\n  __typename\n  id\n  ...SimpleResponseParentEntity_post\n}\n\nfragment StoryResponseParentEntity_post on Post {\n  id\n  ...ResponseHeaderParentEntity_post\n  __typename\n}\n\nfragment ThreadedReplyParentEntity_post on Post {\n  __typename\n  id\n  ...ReadOrEditSimpleResponseParentEntity_post\n  ...StoryResponseParentEntity_post\n}\n\nfragment ThreadedRepliesParentEntity_post on Post {\n  __typename\n  id\n  ...ThreadedReplyParentEntity_post\n}\n\nfragment ThreadedResponsesSidebarContent_post on Post {\n  id\n  latestPublishedVersion\n  postResponses {\n    count\n    __typename\n  }\n  collection {\n    id\n    viewerEdge {\n      id\n      isEditor\n      __typename\n    }\n    __typename\n  }\n  creator {\n    id\n    __typename\n  }\n  ...ThreadedRepliesParentEntity_post\n  __typename\n}\n\nfragment ThreadedResponsesSidebar_post on Post {\n  id\n  ...ThreadedResponsesSidebarContent_post\n  __typename\n}\n\nfragment MultiVoteCount_post on Post {\n  id\n  __typename\n}\n\nfragment MultiVote_post on Post {\n  id\n  creator {\n    id\n    ...SusiClickable_user\n    __typename\n  }\n  isPublished\n  ...SusiClickable_post\n  collection {\n    id\n    slug\n    __typename\n  }\n  isLimitedState\n  ...MultiVoteCount_post\n  __typename\n}\n\nfragment useCopyFriendLink_post on Post {\n  ...usePostUrl_post\n  __typename\n  id\n}\n\nfragment UpsellClickable_post on Post {\n  id\n  collection {\n    id\n    __typename\n  }\n  sequence {\n    sequenceId\n    __typename\n  }\n  creator {\n    id\n    __typename\n  }\n  __typename\n}\n\nfragment FriendLink_post on Post {\n  id\n  ...SusiClickable_post\n  ...useCopyFriendLink_post\n  ...UpsellClickable_post\n  __typename\n}\n\nfragment PostSharePopover_post on Post {\n  id\n  mediumUrl\n  title\n  isPublished\n  isLocked\n  ...usePostUrl_post\n  ...FriendLink_post\n  __typename\n}\n\nfragment ClapMutation_post on Post {\n  __typename\n  id\n  clapCount\n  ...MultiVoteCount_post\n}\n\nfragment OverflowMenuItemUndoClaps_post on Post {\n  id\n  clapCount\n  ...ClapMutation_post\n  __typename\n}\n\nfragment AddToCatalogBase_post on Post {\n  id\n  isPublished\n  ...SusiClickable_post\n  __typename\n}\n\nfragment NegativeSignalModal_publisher on Publisher {\n  __typename\n  id\n  name\n}\n\nfragment NegativeSignalModal_post on Post {\n  id\n  creator {\n    ...NegativeSignalModal_publisher\n    viewerEdge {\n      id\n      isMuting\n      __typename\n    }\n    __typename\n    id\n  }\n  collection {\n    ...NegativeSignalModal_publisher\n    viewerEdge {\n      id\n      isMuting\n      __typename\n    }\n    __typename\n    id\n  }\n  __typename\n}\n\nfragment ExplicitSignalMenuOptions_post on Post {\n  ...NegativeSignalModal_post\n  __typename\n  id\n}\n\nfragment OverflowMenu_post on Post {\n  id\n  creator {\n    id\n    __typename\n  }\n  collection {\n    id\n    __typename\n  }\n  ...OverflowMenuItemUndoClaps_post\n  ...AddToCatalogBase_post\n  ...ExplicitSignalMenuOptions_post\n  __typename\n}\n\nfragment OverflowMenuButton_post on Post {\n  id\n  visibility\n  ...OverflowMenu_post\n  __typename\n}\n\nfragment AddToCatalogBookmarkButton_post on Post {\n  ...AddToCatalogBase_post\n  __typename\n  id\n}\n\nfragment BookmarkButton_post on Post {\n  visibility\n  ...SusiClickable_post\n  ...AddToCatalogBookmarkButton_post\n  __typename\n  id\n}\n\nfragment PostJsonLd_logo on ImageMetadata {\n  id\n  originalWidth\n  originalHeight\n  __typename\n}\n\nfragment PostJsonLd_collection on Collection {\n  id\n  name\n  domain\n  slug\n  logo {\n    ...PostJsonLd_logo\n    __typename\n    id\n  }\n  __typename\n}\n\nfragment getPostContentAsString_post on Post {\n  content(postMeteringOptions: $postMeteringOptions) {\n    bodyModel {\n      paragraphs {\n        text\n        type\n        mixtapeMetadata {\n          href\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment appendPostContext_post on Post {\n  id\n  sequence {\n    title\n    __typename\n  }\n  collection {\n    name\n    __typename\n    id\n  }\n  creator {\n    name\n    __typename\n    id\n  }\n  __typename\n}\n\nfragment maybeAppendProductName_collection on Collection {\n  id\n  domain\n  __typename\n}\n\nfragment postTitle_post on Post {\n  id\n  title\n  seoTitle\n  firstPublishedAt\n  ...getPostContentAsString_post\n  ...appendPostContext_post\n  collection {\n    id\n    name\n    domain\n    ...maybeAppendProductName_collection\n    __typename\n  }\n  creator {\n    name\n    __typename\n    id\n  }\n  previewContent {\n    subtitle\n    __typename\n  }\n  __typename\n}\n\nfragment GetTitleIndexMap_bodyModel on RichText {\n  paragraphs {\n    type\n    text\n    __typename\n  }\n  __typename\n}\n\nfragment getTitleDetails_post on Post {\n  id\n  content(postMeteringOptions: $postMeteringOptions) {\n    bodyModel {\n      ...GetTitleIndexMap_bodyModel\n      __typename\n    }\n    __typename\n  }\n  ...getPostContentAsString_post\n  __typename\n}\n\nfragment getTitleForPost_post on Post {\n  id\n  title\n  ...postTitle_post\n  ...getTitleDetails_post\n  __typename\n}\n\nfragment PostJsonLd_post on Post {\n  id\n  title\n  seoTitle\n  mediumUrl\n  creator {\n    name\n    username\n    ...userUrl_user\n    __typename\n    id\n  }\n  collection {\n    ...PostJsonLd_collection\n    __typename\n    id\n  }\n  previewImage {\n    id\n    focusPercentX\n    focusPercentY\n    originalWidth\n    originalHeight\n    __typename\n  }\n  isLocked\n  firstPublishedAt\n  updatedAt\n  isShortform\n  shortformType\n  ...getTitleForPost_post\n  __typename\n}\n\nfragment postMetaDescription_post on Post {\n  id\n  title\n  seoDescription\n  metaDescription\n  creator {\n    id\n    name\n    __typename\n  }\n  collection {\n    id\n    name\n    __typename\n  }\n  previewContent {\n    subtitle\n    __typename\n  }\n  ...getPostContentAsString_post\n  __typename\n}\n\nfragment shortformPostMetaDescription_post on Post {\n  id\n  metaDescription\n  seoDescription\n  shortformType\n  title\n  ...getPostContentAsString_post\n  __typename\n}\n\nfragment shouldIndexPost_post on Post {\n  id\n  firstPublishedAt\n  isShortform\n  shortformType\n  visibility\n  ...getPostContentAsString_post\n  viewerEdge {\n    shouldIndexPostForExternalSearch\n    __typename\n    id\n  }\n  __typename\n}\n\nfragment shouldFollowPost_post on Post {\n  viewerEdge {\n    shouldFollowPostForExternalSearch\n    __typename\n    id\n  }\n  __typename\n  id\n}\n\nfragment shortformPostTitle_post on Post {\n  id\n  title\n  seoTitle\n  shortformType\n  ...getPostContentAsString_post\n  ...appendPostContext_post\n  collection {\n    ...maybeAppendProductName_collection\n    __typename\n    id\n  }\n  __typename\n}\n\nfragment PostFooterTags_post on Post {\n  id\n  tags {\n    __typename\n    id\n    displayTitle\n    normalizedTagSlug\n  }\n  __typename\n}\n\nfragment OverlappingAvatars_collection on Collection {\n  id\n  name\n  avatar {\n    id\n    __typename\n  }\n  domain\n  slug\n  __typename\n}\n\nfragment OverlappingAvatars_user on User {\n  __typename\n  id\n  imageId\n  name\n  username\n  ...userUrl_user\n}\n\nfragment UserMentionTooltip_user on User {\n  id\n  name\n  bio\n  ...UserAvatar_user\n  ...UserFollowButton_user\n  ...useIsVerifiedBookAuthor_user\n  __typename\n}\n\nfragment AuthorByline_user on User {\n  __typename\n  id\n  name\n  ...useIsVerifiedBookAuthor_user\n  ...userUrl_user\n  ...UserMentionTooltip_user\n  ...UserFollowButton_user\n}\n\nfragment PostByline_user on User {\n  ...AuthorByline_user\n  __typename\n  id\n}\n\nfragment PostBodyInserts_paragraph on Paragraph {\n  name\n  text\n  type\n  __typename\n  id\n}\n\nfragment EntityPresentationRankedModulePublishingTracker_entity on RankedModulePublishingEntity {\n  __typename\n  ... on Collection {\n    id\n    __typename\n  }\n  ... on User {\n    id\n    __typename\n  }\n}\n\nfragment CollectionTooltip_collection on Collection {\n  id\n  name\n  slug\n  description\n  subscriberCount\n  customStyleSheet {\n    header {\n      backgroundImage {\n        id\n        __typename\n      }\n      __typename\n    }\n    __typename\n    id\n  }\n  ...CollectionAvatar_collection\n  ...CollectionFollowButton_collection\n  ...EntityPresentationRankedModulePublishingTracker_entity\n  __typename\n}\n\nfragment CollectionLinkWithPopover_collection on Collection {\n  name\n  ...collectionUrl_collection\n  ...CollectionTooltip_collection\n  __typename\n  id\n}\n\nfragment shouldShowPublishedInStatus_post on Post {\n  statusForCollection\n  isPublished\n  __typename\n  id\n}\n\nfragment CollectionByline_post on Post {\n  ...shouldShowPublishedInStatus_post\n  __typename\n  id\n}\n\nfragment BoldCollectionName_collection on Collection {\n  id\n  name\n  __typename\n}\n\nfragment DraftStatus_post on Post {\n  id\n  pendingCollection {\n    id\n    creator {\n      id\n      __typename\n    }\n    ...BoldCollectionName_collection\n    __typename\n  }\n  statusForCollection\n  creator {\n    id\n    __typename\n  }\n  isPublished\n  __typename\n}\n\nfragment PostBylineDescription_post on Post {\n  id\n  isNewsletter\n  collection {\n    slug\n    ...CollectionLinkWithPopover_collection\n    __typename\n    id\n  }\n  ...CollectionByline_post\n  ...DraftStatus_post\n  __typename\n}\n\nfragment MaybeTextToSpeech_post on Post {\n  id\n  detectedLanguage\n  wordCount\n  isPublished\n  __typename\n}\n\nfragment PostByline_post on Post {\n  id\n  postResponses {\n    count\n    __typename\n  }\n  allowResponses\n  isLimitedState\n  isPublished\n  ...PostBylineDescription_post\n  ...MultiVote_post\n  ...BookmarkButton_post\n  ...MaybeTextToSpeech_post\n  ...PostSharePopover_post\n  ...OverflowMenuButton_post\n  __typename\n}\n\nfragment useShouldShowPostPageMeter_post on Post {\n  id\n  creator {\n    id\n    __typename\n  }\n  isLocked\n  lockedSource\n  content(postMeteringOptions: $postMeteringOptions) {\n    isLockedPreviewOnly\n    validatedShareKey\n    __typename\n  }\n  __typename\n}\n\nfragment FriendLinkSharer_user on User {\n  id\n  name\n  ...userUrl_user\n  __typename\n}\n\nfragment FriendLinkMeter_postContent on PostContent {\n  validatedShareKey\n  shareKeyCreator {\n    ...FriendLinkSharer_user\n    __typename\n    id\n  }\n  __typename\n}\n\nfragment MeterClickable_post on Post {\n  id\n  ...UpsellClickable_post\n  __typename\n}\n\nfragment FriendLinkMeter_post on Post {\n  id\n  content(postMeteringOptions: $postMeteringOptions) {\n    ...FriendLinkMeter_postContent\n    __typename\n  }\n  creator {\n    ...FriendLinkSharer_user\n    __typename\n    id\n  }\n  ...MeterClickable_post\n  __typename\n}\n\nfragment PostPageMeter_post on Post {\n  id\n  content(postMeteringOptions: $postMeteringOptions) {\n    isLockedPreviewOnly\n    __typename\n  }\n  ...FriendLinkMeter_post\n  ...MeterClickable_post\n  __typename\n}\n\nfragment Star_post on Post {\n  id\n  creator {\n    id\n    __typename\n  }\n  isLocked\n  __typename\n}\n\nfragment FeaturedStoryPopover_post on Post {\n  id\n  collection {\n    id\n    name\n    slug\n    ...CollectionAvatar_collection\n    __typename\n  }\n  __typename\n}\n\nfragment FeaturedStoryLabel_post on Post {\n  isFeaturedInPublishedPublication\n  id\n  creator {\n    id\n    __typename\n  }\n  collection {\n    id\n    __typename\n  }\n  ...FeaturedStoryPopover_post\n  __typename\n}\n\nfragment StarAndFeaturedInsert_post on Post {\n  isLocked\n  ...Star_post\n  ...FeaturedStoryLabel_post\n  __typename\n  id\n}\n\nfragment usePostClientViewedReporter_post on Post {\n  id\n  isPublished\n  isLocked\n  collection {\n    id\n    slug\n    __typename\n  }\n  content(postMeteringOptions: $postMeteringOptions) {\n    validatedShareKey\n    isLockedPreviewOnly\n    __typename\n  }\n  __typename\n}\n\nfragment buildBranchViewData_post on Post {\n  creator {\n    name\n    id\n    __typename\n  }\n  collection {\n    name\n    id\n    __typename\n  }\n  layerCake\n  primaryTopic {\n    id\n    slug\n    name\n    __typename\n  }\n  content(postMeteringOptions: $postMeteringOptions) {\n    isLockedPreviewOnly\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment usePostBranchView_post on Post {\n  id\n  isPublished\n  isLocked\n  collection {\n    id\n    slug\n    domain\n    __typename\n  }\n  ...buildBranchViewData_post\n  __typename\n}\n\nfragment PostResponseParentEntity_post on Post {\n  ...ReadOrEditSimpleResponseParentEntity_post\n  ...StoryResponseParentEntity_post\n  __typename\n  id\n}\n\nfragment PostResponsesContent_post on Post {\n  responsesLocked\n  postResponses {\n    count\n    __typename\n  }\n  creator {\n    id\n    __typename\n  }\n  collection {\n    viewerEdge {\n      isEditor\n      __typename\n      id\n    }\n    __typename\n    id\n  }\n  ...PostResponseParentEntity_post\n  __typename\n  id\n}\n\nfragment PostResultError_postResult on PostResult {\n  __typename\n  ... on Post {\n    id\n    __typename\n  }\n  ... on UnavailableForLegalReasons {\n    ...UnavailableForLegalReasonsScreen_unavailableForLegalReasons\n    __typename\n  }\n  ... on WithheldInCountry {\n    ...WithheldInCountryScreen_withheldInCountry\n    __typename\n  }\n}\n\nfragment FloatingPublicationBio_collection on Collection {\n  id\n  ...CollectionAvatar_collection\n  ...PublisherDescription_publisher\n  ...CollectionFollowButton_collection\n  __typename\n}\n\nfragment MoreFromAuthorAndMaybePub_collection on Collection {\n  id\n  name\n  ...collectionUrl_collection\n  __typename\n}\n\nfragment PostPublishersInfoSection_collection on Collection {\n  ...PostPublisherInfo_publisher\n  __typename\n  id\n}\n\nfragment PublicationNav_collection on Collection {\n  id\n  name\n  slug\n  ...PublicationNavColorBar_collection\n  ...PublicationNavMobileItems_collection\n  __typename\n}\n\nfragment MastodonVerificationLink_user on User {\n  id\n  linkedAccounts {\n    mastodon {\n      domain\n      username\n      __typename\n      id\n    }\n    __typename\n    id\n  }\n  __typename\n}\n\nfragment SuspendedBannerLoader_user on User {\n  id\n  isSuspended\n  __typename\n}\n\nfragment MoreFromAuthorAndMaybePub_user on User {\n  __typename\n  id\n  name\n  imageId\n  ...userUrl_user\n}\n\nfragment PostPublishersInfoSection_user on User {\n  ...PostPublisherInfo_publisher\n  __typename\n  id\n}\n\nfragment Wall_post on Post {\n  content(postMeteringOptions: $postMeteringOptions) {\n    isLockedPreviewOnly\n    __typename\n  }\n  isLocked\n  isMarkedPaywallOnly\n  ...RegWall_post\n  ...Paywall_post\n  __typename\n  id\n}\n\nfragment InteractivePostBody_post on Post {\n  id\n  isLimitedState\n  isPublished\n  allowResponses\n  content(postMeteringOptions: $postMeteringOptions) {\n    isLockedPreviewOnly\n    bodyModel {\n      ...PostBody_bodyModel\n      paragraphs {\n        ...HighlighSegmentContext_paragraph\n        ...NormalizeHighlights_paragraph\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  creator {\n    id\n    allowNotes\n    __typename\n  }\n  ...ActiveSelectionContext_post\n  __typename\n}\n\nfragment WithResponsesSidebar_post on Post {\n  id\n  ...ThreadedResponsesSidebar_post\n  __typename\n}\n\nfragment PostCanonicalizer_post on Post {\n  mediumUrl\n  __typename\n  id\n}\n\nfragment PostFooterActionsBar_post on Post {\n  id\n  visibility\n  allowResponses\n  postResponses {\n    count\n    __typename\n  }\n  isLimitedState\n  creator {\n    id\n    __typename\n  }\n  collection {\n    id\n    __typename\n  }\n  ...MultiVote_post\n  ...PostSharePopover_post\n  ...OverflowMenuButton_post\n  ...BookmarkButton_post\n  __typename\n}\n\nfragment PostReadTracker_post on Post {\n  id\n  collection {\n    slug\n    __typename\n    id\n  }\n  sequence {\n    sequenceId\n    __typename\n  }\n  content(postMeteringOptions: $postMeteringOptions) {\n    isLockedPreviewOnly\n    __typename\n  }\n  __typename\n}\n\nfragment PostMetadata_post on Post {\n  id\n  socialTitle\n  socialDek\n  canonicalUrl\n  mediumUrl\n  metaDescription\n  latestPublishedAt\n  visibility\n  isLimitedState\n  readingTime\n  creator {\n    name\n    twitterScreenName\n    ...userUrl_user\n    __typename\n    id\n  }\n  collection {\n    twitterUsername\n    facebookPageId\n    __typename\n    id\n  }\n  previewContent {\n    subtitle\n    __typename\n  }\n  previewImage {\n    id\n    alt\n    focusPercentX\n    focusPercentY\n    originalHeight\n    originalWidth\n    __typename\n  }\n  isShortform\n  ...PostJsonLd_post\n  ...postMetaDescription_post\n  ...shortformPostMetaDescription_post\n  ...shouldIndexPost_post\n  ...shouldFollowPost_post @include(if: $includeShouldFollowPost)\n  ...shortformPostTitle_post\n  ...getTitleDetails_post\n  ...getTitleForPost_post\n  __typename\n}\n\nfragment SuspendedBannerLoader_post on Post {\n  id\n  isSuspended\n  __typename\n}\n\nfragment PostFooterInfo_post on Post {\n  id\n  license\n  visibility\n  ...PostFooterTags_post\n  __typename\n}\n\nfragment PostBodyInserts_post on Post {\n  collection {\n    ...OverlappingAvatars_collection\n    __typename\n    id\n  }\n  creator {\n    ...OverlappingAvatars_user\n    ...PostByline_user\n    __typename\n    id\n  }\n  firstPublishedAt\n  isLocked\n  isShortform\n  readingTime\n  isFeaturedInPublishedPublication\n  content(postMeteringOptions: $postMeteringOptions) {\n    isLockedPreviewOnly\n    bodyModel {\n      paragraphs {\n        ...PostBodyInserts_paragraph\n        __typename\n      }\n      sections {\n        startIndex\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  ...PostByline_post\n  ...useShouldShowPostPageMeter_post\n  ...PostPageMeter_post\n  ...StarAndFeaturedInsert_post\n  __typename\n  id\n}\n\nfragment PostNoteMissingToast_post on Post {\n  id\n  __typename\n}\n\nfragment usePostTracking_post on Post {\n  ...usePostClientViewedReporter_post\n  ...usePostBranchView_post\n  __typename\n  id\n}\n\nfragment InResponseToEntityPreview_post on Post {\n  id\n  inResponseToEntityType\n  __typename\n}\n\nfragment PostPublishedDialog_prerequisite_post on Post {\n  id\n  creator {\n    id\n    __typename\n  }\n  collection {\n    id\n    __typename\n  }\n  __typename\n}\n\nfragment PostResponses_post on Post {\n  isPublished\n  allowResponses\n  isLimitedState\n  ...PostResponsesContent_post\n  __typename\n  id\n}\n"
        }
    ]
    gql_json = utils.post_url(graphql_url, json_data=data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    post_json = gql_json[0]['data']['postResult']

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['mediumUrl']
    item['title'] = post_json['title']

    dt = datetime.fromtimestamp(post_json['firstPublishedAt'] / 1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = datetime.fromtimestamp(post_json['updatedAt'] / 1000).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    if post_json.get('creator'):
        item['author'] = {}
        item['author']['name'] = post_json['creator']['name']

    item['tags'] = []
    if post_json.get('tags'):
        for it in post_json['tags']:
            if it.get('displayTitle'):
                item['tags'].append(it['displayTitle'])
            else:
                item['tags'].append(it['normalizedTagSlug'])
    if post_json.get('topics'):
        for it in post_json['topics']:
            if it.get('name'):
                item['tags'].append(item['name'])
            else:
                item['tags'].append(it['slug'])
    if item.get('tags'):
        item['tags'] = list(set(item['tags']))
    else:
        del item['tags']

    if post_json.get('previewImage') and post_json['previewImage'].get('id'):
        item['_image'] = 'https://miro.medium.com/max/1000/{}'.format(post_json['previewImage']['id'])

    if post_json.get('previewContent'):
        item['summary'] = post_json['previewContent']['subtitle']

    item['content_html'] = ''
    if post_json['content']['isLockedPreviewOnly']:
        # The googlecache version seems to have the full text
        content_json = get_apollo_state_content(url)
        if content_json:
            if save_debug:
                utils.write_file(content_json, './debug/content.json')
        else:
            content_json = post_json['content']
    else:
        content_json = post_json['content']
    for paragraph in content_json['bodyModel']['paragraphs']:
        paragraph_type = paragraph['type'].lower()
        start_tag = ''
        if paragraph_type == 'p' or paragraph_type == 'h1' or paragraph_type == 'h2' or paragraph_type == 'h3' or paragraph_type == 'h4':
            start_tag += '<{}>'.format(paragraph_type)
            paragraph_text = paragraph['text']
            end_tag = '</{}>'.format(paragraph_type)

        elif paragraph_type == 'img':
            start_tag = add_image(paragraph['metadata'], paragraph['text'])
            end_tag = ''
            paragraph_text = ''

        elif paragraph_type == 'pre':
            start_tag += '<pre style="padding:0.5em; white-space:pre-wrap; background:light-dark(#ccc, #333);">'
            end_tag = '</pre>'
            if not paragraph.get('markups'):
                # Escape HTML characters so they are not rendered
                paragraph_text = html.escape(paragraph['text'])
            else:
                # If there are markups, escaping the characters will mess up the alignment
                paragraph_text = paragraph['text']

        elif paragraph_type == 'bq' or paragraph_type == 'pq':
            start_tag += '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;">'
            end_tag = '</blockquote>'
            paragraph_text = paragraph['text']

        elif paragraph_type == 'oli' or paragraph_type == 'uli':
            start_tag = '<{}l><li>'.format(paragraph_type[0])
            end_tag = '</li></{}l>'.format(paragraph_type[0])
            paragraph_text = paragraph['text']

        elif paragraph_type == 'iframe':
            media_resource = paragraph['iframe']['mediaResource']
            iframe_src = media_resource['iframeSrc']
            if iframe_src.startswith('https://cdn.embedly.com'):
                # This is usually embeded media
                iframe_query = parse_qs(urlsplit(iframe_src).query)
                if 'src' in iframe_query:
                    iframe_src = iframe_query['src'][0]
                elif 'url' in iframe_query:
                    iframe_src = iframe_query['url'][0]
                start_tag += utils.add_embed(iframe_src)
                end_tag = ''
                paragraph_text = ''
            elif not iframe_src:
                iframe_html = utils.get_url_html('{}://{}/media/{}'.format(split_url.scheme, split_url.netloc, media_resource['id']))
                if iframe_html:
                    if save_debug:
                        utils.write_file(iframe_html, './debug/iframe.html')
                    m = re.search(r'src="https:\/\/gist\.github\.com\/([^\/]+)\/([^\.]+)\.js"', iframe_html)
                    if m:
                        gist = utils.get_url_html('https://gist.githubusercontent.com/{}/{}/raw'.format(m.group(1), m.group(2)))
                        if gist:
                            start_tag += '<pre style="padding:0.5em; white-space:pre-wrap; background:light-dark(#ccc, #333);">{}</pre>'.format(gist)
                            end_tag = ''
                            paragraph_text = ''
                if not start_tag:
                    logger.warning('unhandled Medium media iframe in ' + item['url'])
            else:
                logger.warning('unhandled Medium iframe content in ' + item['url'])
                start_tag += '<p>Embedded content from <a href="{0}">{0}</a></p>'.format(iframe_src)
                end_tag = ''
                paragraph_text = ''

        elif paragraph_type == 'mixtape_embed':
            # start_tag += '<blockquote><ul><li>'
            # end_tag = '</li></ul></blockquote>'
            # paragraph_text = paragraph['text']
            src = urlsplit(paragraph['mixtapeMetadata']['href']).netloc
            paragraph_text = re.sub(r'…{}'.format(src), '', paragraph['text'])
            if paragraph['mixtapeMetadata'].get('thumbnailImageId'):
                start_tag += '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
                start_tag += '<div style="flex:1; min-width:256px; max-width:360px;"><a href="{}" target="_blank"><img src="https://miro.medium.com/max/640/{}" style="width:100%;" /></a></div>'.format(paragraph['mixtapeMetadata']['href'], paragraph['mixtapeMetadata']['thumbnailImageId'])
                start_tag += '<div style="flex:2; min-width:256px;">'
                end_tag = '<div><small>{}</small></div></div></div>'.format(src)
            else:
                start_tag += '<blockquote>'
                end_tag = '<br/><small>{}</small></blockquote>'.format(src)
        else:
            logger.warning('unhandled paragraph type {} in {}'.format(paragraph_type, url))
            continue

        if paragraph.get('markups'):
            starts = list(map(operator.itemgetter('start'), paragraph['markups']))
            ends = list(map(operator.itemgetter('end'), paragraph['markups']))
            markup_text = paragraph_text[0:min(starts)]
            for i in range(min(starts), max(ends) + 1):
                for n in range(len(starts)):
                    if starts[n] == i:
                        markup_type = paragraph['markups'][n]['type'].lower()
                        if markup_type == 'a':
                            href = ''
                            if paragraph['markups'][n]['anchorType'] == 'LINK':
                                href = paragraph['markups'][n]['href']
                            elif paragraph['markups'][n]['anchorType'] == 'USER':
                                href = 'https://medium.com/u/' + paragraph['markups'][n]['userId']
                            if href:
                                markup_text += '<a href="{}">'.format(href)
                            else:
                                logger.warning('unhandled anchor markup type {} in {}'.format(paragraph['markups'][n]['anchorType'], item['url']))
                                markup_text += '<a href="https://medium.com">'
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

            markup_text += paragraph_text[i + 1:]
        else:
            markup_text = paragraph_text
        markup_text = markup_text.replace('\n', '<br />')

        if paragraph_type == 'p' and paragraph.get('hasDropCap') and paragraph['hasDropCap']:
            if not markup_text.startswith('<'):
                markup_text = '<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}'.format(markup_text[0], markup_text[1:])
                end_tag += '<div style="clear:left;"></div>'
            else:
                logger.warning('unhandled DropCap in ' + item['url'])

        item['content_html'] += start_tag + markup_text + end_tag

    item['content_html'] = item['content_html'].replace('</ol><ol>', '').replace('</ul><ul>', '')
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
