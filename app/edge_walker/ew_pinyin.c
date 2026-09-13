/****************************************************************************
 * 拼音词组 + 常用音节汉字（按最长音节切分）
 ****************************************************************************/

#include "ew_pinyin.h"

#include <string.h>
#include <stddef.h>

typedef struct {
  const char *py;
  const char *zh;
} ew_py_t;

/* 词组：长词在前 */
static const ew_py_t g_words[] = {
  {"weishenme", "为什么"}, {"zenmeyang", "怎么样"}, {"zenmeban", "怎么办"},
  {"bianyuan", "边缘"}, {"xingzhe", "行者"}, {"zhineng", "智能"},
  {"moxing", "模型"}, {"jiqiren", "机器人"}, {"duihua", "对话"},
  {"shuru", "输入"}, {"shurufa", "输入法"}, {"hanyu", "汉语"},
  {"zhongwen", "中文"}, {"yingwen", "英文"}, {"pinyin", "拼音"},
  {"gaojing", "告警"}, {"yujing", "预警"}, {"jingbao", "警报"},
  {"leida", "雷达"}, {"juli", "距离"}, {"sudu", "速度"},
  {"zhuangtai", "状态"}, {"xianzai", "现在"}, {"jieshao", "介绍"},
  {"bangzhu", "帮助"}, {"jieshi", "解释"}, {"gongzuo", "工作"},
  {"xingren", "行人"}, {"dianche", "电车"}, {"anquan", "安全"},
  {"jinji", "紧急"}, {"kaiguan", "开关"}, {"wangluo", "网络"},
  {"fuwu", "服务"}, {"qingqiu", "请求"}, {"huida", "回答"},
  {"wenti", "问题"}, {"ceshi", "测试"}, {"xitong", "系统"},
  {"shebei", "设备"}, {"pingmu", "屏幕"}, {"jianpan", "键盘"},
  {"nihao", "你好"}, {"xiexie", "谢谢"}, {"duibuqi", "对不起"},
  {"shenme", "什么"}, {"zenme", "怎么"}, {"weishen", "为什"},
  {"keyi", "可以"}, {"buneng", "不能"}, {"nashi", "那是"},
  {"zheshi", "这是"}, {"woshi", "我是"}, {"nishi", "你是"},
  {"dakai", "打开"}, {"guanbi", "关闭"}, {"fanhui", "返回"},
  {"qidong", "启动"}, {"tingzhi", "停止"}, {NULL, NULL}
};

/* 音节 -> 常用字（UTF-8 连写） */
static const ew_py_t g_syl[] = {
  {"a", "啊阿"}, {"ai", "爱哎哀矮艾碍"}, {"an", "安按暗案"},
  {"ang", "昂"}, {"ao", "奥傲熬凹澳"},
  {"ba", "把八吧巴爸罢拔"}, {"bai", "白百摆败拜"},
  {"ban", "办半板班般版伴"}, {"bang", "帮棒旁邦绑"},
  {"bao", "包报保宝抱暴薄"}, {"bei", "被北备背倍杯悲"},
  {"ben", "本奔"}, {"beng", "崩蹦绷"},
  {"bi", "比必笔闭避币彼毕"}, {"bian", "边变便遍编辨"},
  {"biao", "表标彪"}, {"bie", "别憋"},
  {"bin", "宾滨彬"}, {"bing", "并病冰兵饼"},
  {"bo", "波博播伯玻拨薄"}, {"bu", "不部步布补捕"},
  {"ca", "擦"}, {"cai", "才菜采彩财猜"},
  {"can", "参残餐惨灿"}, {"cang", "藏仓苍舱"},
  {"cao", "草操曹槽"}, {"ce", "测策侧册"},
  {"cen", "岑"}, {"ceng", "层曾蹭"},
  {"cha", "查差茶插叉察"}, {"chai", "拆柴"},
  {"chan", "产缠禅阐颤"}, {"chang", "长常场唱厂畅"},
  {"chao", "超朝潮吵抄巢"}, {"che", "车彻撤尺"},
  {"chen", "陈沉晨尘称衬"}, {"cheng", "成城程称承乘"},
  {"chi", "吃持迟赤尺池齿"}, {"chong", "冲重充虫崇"},
  {"chou", "抽愁丑仇筹臭"}, {"chu", "出初除处楚触"},
  {"chuai", "揣踹"}, {"chuan", "传穿船川串"},
  {"chuang", "创窗床闯"}, {"chui", "吹垂锤"},
  {"chun", "春纯唇"}, {"chuo", "戳绰"},
  {"ci", "此次词刺磁辞"}, {"cong", "从聪丛匆"},
  {"cou", "凑"}, {"cu", "粗促醋簇"},
  {"cuan", "窜攒"}, {"cui", "催脆翠"},
  {"cun", "村存寸"}, {"cuo", "错措挫搓"},
  {"da", "大打达答搭"}, {"dai", "带代待呆戴袋"},
  {"dan", "但单担弹淡胆蛋"}, {"dang", "当党档挡荡"},
  {"dao", "到道倒导刀岛盗"}, {"de", "的得德地"},
  {"dei", "得"}, {"deng", "等灯登邓瞪"},
  {"di", "地第低底弟帝敌"}, {"dian", "点电店典殿垫"},
  {"diao", "掉调雕吊钓"}, {"die", "跌叠蝶爹"},
  {"ding", "定顶丁订盯钉"}, {"diu", "丢"},
  {"dong", "东动懂冬洞冻"}, {"dou", "都斗豆抖陡"},
  {"du", "读度独毒堵渡督"}, {"duan", "段短断端锻"},
  {"dui", "对队堆兑"}, {"dun", "顿盾吨蹲"},
  {"duo", "多夺朵躲堕"},
  {"e", "额恶饿俄鹅"}, {"en", "恩"}, {"er", "而二儿尔耳"},
  {"fa", "发法罚乏伐"}, {"fan", "反饭范繁翻凡"},
  {"fang", "方放房防访纺"}, {"fei", "非飞费肥废肺"},
  {"fen", "分份纷奋粉愤"}, {"feng", "风封峰丰冯缝"},
  {"fo", "佛"}, {"fou", "否"},
  {"fu", "服父复府负富妇付"},
  {"ga", "嘎尬夹"}, {"gai", "该改概盖钙"},
  {"gan", "干感敢赶甘杆"}, {"gang", "刚钢港岗纲"},
  {"gao", "高告搞稿膏"}, {"ge", "个各格歌哥隔"},
  {"gei", "给"}, {"gen", "根跟"},
  {"geng", "更耕耿"}, {"gong", "工公功共供宫攻"},
  {"gou", "够构狗沟购钩"}, {"gu", "古故顾股骨固谷"},
  {"gua", "挂瓜刮寡"}, {"guai", "怪乖拐"},
  {"guan", "关管观官馆惯冠"}, {"guang", "光广逛"},
  {"gui", "规贵归鬼轨桂"}, {"gun", "滚棍"},
  {"guo", "过国果郭锅裹"},
  {"ha", "哈"}, {"hai", "还海害孩亥"},
  {"han", "汉含寒喊汗韩函"}, {"hang", "行航杭"},
  {"hao", "好号毫豪耗浩"}, {"he", "和何合河喝核盒"},
  {"hei", "黑嘿"}, {"hen", "很恨狠痕"},
  {"heng", "横恒衡"}, {"hong", "红洪宏轰鸿"},
  {"hou", "后候厚猴侯"}, {"hu", "护户互湖呼胡虎"},
  {"hua", "话化花华划画滑"}, {"huai", "坏怀淮"},
  {"huan", "还换环欢缓患"}, {"huang", "黄皇荒慌晃"},
  {"hui", "会回灰挥汇惠毁"}, {"hun", "混昏婚魂"},
  {"huo", "或活火货获伙"},
  {"ji", "机及己几集记计极"}, {"jia", "家加价假架甲夹"},
  {"jian", "见间件建简减坚"}, {"jiang", "将讲江降奖姜"},
  {"jiao", "教交叫较脚角焦"}, {"jie", "解接结界阶姐借"},
  {"jin", "进金今近尽紧仅"}, {"jing", "经精京静境警景"},
  {"jiong", "窘炯"}, {"jiu", "就九久旧酒救究"},
  {"ju", "据具局举句居剧距"}, {"juan", "卷圈捐倦"},
  {"jue", "觉决绝掘角"}, {"jun", "军均君俊"},
  {"ka", "卡喀咖"}, {"kai", "开凯慨楷"},
  {"kan", "看刊砍堪"}, {"kang", "抗康扛"},
  {"kao", "考靠烤拷"}, {"ke", "可科克客刻课颗"},
  {"ken", "肯恳垦"}, {"keng", "坑"},
  {"kong", "空控恐孔"}, {"kou", "口扣寇"},
  {"ku", "苦库哭酷裤"}, {"kua", "跨夸垮"},
  {"kuai", "快块筷会"}, {"kuan", "宽款"},
  {"kuang", "况矿狂框"}, {"kui", "亏愧魁窥"},
  {"kun", "困昆捆"}, {"kuo", "扩括阔"},
  {"la", "拉啦辣腊蜡"}, {"lai", "来赖莱"},
  {"lan", "蓝兰栏懒览滥"}, {"lang", "浪郎朗狼廊"},
  {"lao", "老劳牢捞烙"}, {"le", "了乐勒"},
  {"lei", "类雷累泪磊"}, {"leng", "冷愣棱"},
  {"li", "里理力立利李历离"}, {"lia", "俩"},
  {"lian", "连联脸练恋莲"}, {"liang", "两量亮良粮辆"},
  {"liao", "了料疗聊辽廖"}, {"lie", "列烈裂猎劣"},
  {"lin", "林临邻淋麟"}, {"ling", "领另令灵零龄"},
  {"liu", "六流留刘柳陆"}, {"long", "龙隆笼拢"},
  {"lou", "楼漏露搂陋"}, {"lu", "路陆录鲁炉鹿"},
  {"luan", "乱卵峦"}, {"lue", "略掠"}, {"lv", "律绿率旅铝虑"},
  {"lun", "论轮伦仑"}, {"luo", "落罗络洛逻裸"},
  {"ma", "吗妈马麻码骂嘛"}, {"mai", "买卖麦埋迈"},
  {"man", "满慢漫蛮瞒"}, {"mang", "忙盲茫芒"},
  {"mao", "毛冒帽貌矛茂"}, {"me", "么麽"},
  {"mei", "没美每妹梅媒眉"}, {"men", "们门闷"},
  {"meng", "梦猛蒙盟孟"}, {"mi", "米密迷秘蜜弥"},
  {"mian", "面免棉眠绵"}, {"miao", "秒苗描妙庙"},
  {"mie", "灭蔑"}, {"min", "民敏闽"},
  {"ming", "明名命鸣铭"}, {"miu", "谬"},
  {"mo", "模摸摩末莫墨默膜"}, {"mou", "某谋牟"},
  {"mu", "目母木亩幕慕牧"},
  {"na", "那拿哪纳呐"}, {"nai", "奶耐乃"},
  {"nan", "难南男"}, {"nang", "囊"},
  {"nao", "脑闹恼挠"}, {"ne", "呢讷"},
  {"nei", "内馁"}, {"nen", "嫩"},
  {"neng", "能"}, {"ni", "你尼泥拟逆呢"},
  {"nian", "年念粘捻碾"}, {"niang", "娘酿"},
  {"niao", "鸟尿"}, {"nie", "捏聂镍"},
  {"nin", "您"}, {"ning", "宁凝拧泞"},
  {"niu", "牛扭纽"}, {"nong", "农浓弄"},
  {"nu", "努怒奴"}, {"nuan", "暖"},
  {"nue", "虐"}, {"nuo", "诺挪懦"}, {"nv", "女"},
  {"o", "哦喔噢"}, {"ou", "欧偶呕藕"},
  {"pa", "怕爬帕拍琶"}, {"pai", "排派牌拍迫"},
  {"pan", "盘判盼叛攀"}, {"pang", "旁胖庞"},
  {"pao", "跑炮泡抛袍"}, {"pei", "配陪培佩沛"},
  {"pen", "喷盆"}, {"peng", "朋碰彭棚蓬"},
  {"pi", "批皮匹疲辟啤"}, {"pian", "片便偏篇骗"},
  {"piao", "票漂飘"}, {"pie", "撇瞥"},
  {"pin", "品贫拼频聘"}, {"ping", "平评凭瓶屏苹"},
  {"po", "破迫婆坡颇泼"}, {"pou", "剖"},
  {"pu", "普扑铺仆谱浦"},
  {"qi", "起其期七气齐奇企"}, {"qia", "恰卡掐"},
  {"qian", "前千钱签浅迁欠"}, {"qiang", "强枪墙抢腔"},
  {"qiao", "桥悄巧乔瞧敲"}, {"qie", "且切窃茄"},
  {"qin", "亲侵琴勤秦寝"}, {"qing", "请情清青轻庆"},
  {"qiong", "穷琼"}, {"qiu", "求球秋丘仇"},
  {"qu", "去取区曲趣驱渠"}, {"quan", "全权泉圈劝拳"},
  {"que", "却确缺雀鹊"}, {"qun", "群裙"},
  {"ran", "然燃染冉"}, {"rang", "让壤嚷"},
  {"rao", "绕扰饶"}, {"re", "热惹"},
  {"ren", "人认任仁忍韧"}, {"reng", "仍扔"},
  {"ri", "日"}, {"rong", "容荣融绒溶"},
  {"rou", "肉柔揉"}, {"ru", "如入乳儒辱"},
  {"ruan", "软阮"}, {"rui", "瑞锐蕊"},
  {"run", "润闰"}, {"ruo", "若弱"},
  {"sa", "撒萨洒"}, {"sai", "赛塞腮"},
  {"san", "三散伞"}, {"sang", "桑丧嗓"},
  {"sao", "扫骚嫂"}, {"se", "色瑟涩"},
  {"sen", "森"}, {"seng", "僧"},
  {"sha", "沙杀傻纱刹厦"}, {"shai", "晒筛"},
  {"shan", "山善闪衫扇擅"}, {"shang", "上商伤尚赏"},
  {"shao", "少绍烧稍勺哨"}, {"she", "社设射舍涉蛇"},
  {"shei", "谁"}, {"shen", "什身深神申甚"},
  {"sheng", "生声省胜升盛"}, {"shi", "是时事十实使市识"},
  {"shou", "手受收首守授寿"}, {"shu", "书数树属术输熟"},
  {"shua", "刷耍"}, {"shuai", "帅摔衰率"},
  {"shuan", "栓拴"}, {"shuang", "双爽霜"},
  {"shui", "水谁睡税"}, {"shun", "顺瞬"},
  {"shuo", "说硕朔"}, {"si", "四死思似司丝私"},
  {"song", "送松宋颂诵"}, {"sou", "搜艘嗽"},
  {"su", "速素苏诉宿塑"}, {"suan", "算酸蒜"},
  {"sui", "随岁碎虽遂髓"}, {"sun", "孙损笋"},
  {"suo", "所缩锁索"},
  {"ta", "他她它踏塔"}, {"tai", "太台态抬泰胎"},
  {"tan", "谈弹探坦叹贪坛"}, {"tang", "堂唐糖躺汤趟"},
  {"tao", "套讨逃桃陶淘"}, {"te", "特"},
  {"teng", "腾疼藤"}, {"ti", "体提题替梯踢"},
  {"tian", "天田甜填添"}, {"tiao", "条调跳挑"},
  {"tie", "铁贴"}, {"ting", "听停庭挺厅"},
  {"tong", "同通统痛童铜"}, {"tou", "头投透偷"},
  {"tu", "图土突途徒涂"}, {"tuan", "团"},
  {"tui", "推退腿褪"}, {"tun", "吞屯囤"},
  {"tuo", "托脱拖妥驼"},
  {"wa", "瓦挖哇娃袜"}, {"wai", "外歪"},
  {"wan", "完万晚碗湾玩"}, {"wang", "王往网忘望亡"},
  {"wei", "为位未委维围微危"}, {"wen", "问文温闻稳纹"},
  {"weng", "翁嗡"}, {"wo", "我握卧沃窝"},
  {"wu", "无五物务武误屋"},
  {"xi", "西系喜细希息习席"}, {"xia", "下夏吓峡侠狭"},
  {"xian", "先现线显限县险"}, {"xiang", "想向相象香项乡"},
  {"xiao", "小笑校效消晓销"}, {"xie", "些写谢协鞋斜血"},
  {"xin", "新心信欣辛薪"}, {"xing", "行形型星兴性姓醒"},
  {"xiong", "雄兄胸凶熊"}, {"xiu", "修休秀袖宿锈"},
  {"xu", "需许续须虚序绪"}, {"xuan", "选宣旋悬玄"},
  {"xue", "学血雪穴削"}, {"xun", "寻训讯迅询循"},
  {"ya", "压呀牙亚雅芽"}, {"yan", "眼言研严演验延"},
  {"yang", "样阳杨养洋央羊"}, {"yao", "要药摇腰咬邀遥"},
  {"ye", "也业夜叶野液页"}, {"yi", "一以已意义依医易"},
  {"yin", "因音引银印阴饮"}, {"ying", "应影英营迎硬映"},
  {"yo", "哟"}, {"yong", "用永勇拥涌庸"},
  {"you", "有又由友游右优油"}, {"yu", "于与语育鱼雨余预"},
  {"yuan", "元员原远院愿园"}, {"yue", "月约越乐阅跃"},
  {"yun", "云运允匀韵孕"},
  {"za", "杂砸扎咱"}, {"zai", "在再载灾仔宰"},
  {"zan", "咱赞暂攒"}, {"zang", "脏葬藏"},
  {"zao", "早造遭糟澡灶"}, {"ze", "则责泽择"},
  {"zei", "贼"}, {"zen", "怎"},
  {"zeng", "增曾赠憎"}, {"zha", "扎炸闸渣眨诈"},
  {"zhai", "摘窄债宅斋"}, {"zhan", "站战展占沾詹"},
  {"zhang", "长张章掌仗胀账"}, {"zhao", "找照招着赵兆"},
  {"zhe", "这着者折哲遮"}, {"zhei", "这"},
  {"zhen", "真阵镇针振珍诊"}, {"zheng", "正整争政证征郑"},
  {"zhi", "之只知至制直指值"}, {"zhong", "中种重众终钟忠"},
  {"zhou", "周州洲舟轴昼"}, {"zhu", "主住注助著朱逐"},
  {"zhua", "抓爪"}, {"zhuai", "拽"},
  {"zhuan", "转专传砖赚"}, {"zhuang", "装状壮撞庄"},
  {"zhui", "追坠缀"}, {"zhun", "准"},
  {"zhuo", "桌着卓捉浊"}, {"zi", "子自字资紫仔兹"},
  {"zong", "总宗纵踪综"}, {"zou", "走奏揍"},
  {"zu", "组足族祖阻租"}, {"zuan", "钻攥"},
  {"zui", "最嘴罪醉"}, {"zun", "尊遵"},
  {"zuo", "做作坐左昨座"},
  {NULL, NULL}
};

static int utf8_len(const unsigned char *s)
{
  if (*s < 0x80) {
    return 1;
  }
  if (*s < 0xE0) {
    return 2;
  }
  if (*s < 0xF0) {
    return 3;
  }
  return 4;
}

static int already(char out[][20], int n, const char *zh)
{
  int i;

  for (i = 0; i < n; i++) {
    if (strcmp(out[i], zh) == 0) {
      return 1;
    }
  }
  return 0;
}

static int add_one(char out[][20], unsigned cons[], int n, int max,
                   const char *zh, unsigned eat)
{
  if (n >= max || zh == NULL || zh[0] == '\0' || already(out, n, zh)) {
    return n;
  }
  strncpy(out[n], zh, 19);
  out[n][19] = '\0';
  cons[n] = eat;
  return n + 1;
}

int ew_pinyin_lookup(const char *py, int start, char out[][20],
                     unsigned cons[], int max)
{
  int n = 0;
  int i;
  int skip = start < 0 ? 0 : start;
  int seen = 0;
  size_t pyl;
  int best_i = -1;
  size_t best_l = 0;
  char tmp[8];

  if (py == NULL || py[0] == '\0' || out == NULL || cons == NULL || max <= 0) {
    return 0;
  }
  pyl = strlen(py);

  for (i = 0; g_words[i].py != NULL; i++) {
    size_t wl = strlen(g_words[i].py);
    int hit = 0;
    unsigned eat = (unsigned)pyl;

    if (strncmp(g_words[i].py, py, pyl) == 0) {
      hit = 1;
      eat = (unsigned)pyl;
    } else if (pyl >= wl && strncmp(py, g_words[i].py, wl) == 0) {
      hit = 1;
      eat = (unsigned)wl;
    }
    if (!hit) {
      continue;
    }
    if (seen++ < skip) {
      continue;
    }
    n = add_one(out, cons, n, max, g_words[i].zh, eat);
    if (n >= max) {
      return n;
    }
  }

  for (i = 0; g_syl[i].py != NULL; i++) {
    size_t sl = strlen(g_syl[i].py);
    if (pyl >= sl && strncmp(py, g_syl[i].py, sl) == 0 && sl > best_l) {
      best_l = sl;
      best_i = i;
    }
  }
  if (best_i >= 0) {
    const unsigned char *p = (const unsigned char *)g_syl[best_i].zh;
    int L;
    while (*p != '\0' && n < max) {
      L = utf8_len(p);
      if ((int)strlen((const char *)p) < L) {
        break;
      }
      memcpy(tmp, p, (size_t)L);
      tmp[L] = '\0';
      if (seen++ < skip) {
        p += L;
        continue;
      }
      n = add_one(out, cons, n, max, tmp, (unsigned)best_l);
      p += L;
    }
    if (n >= max) {
      return n;
    }
  }

  /* 还在打这个音节：m / mo / xing 前缀 */
  for (i = 0; g_syl[i].py != NULL && n < max; i++) {
    if (strncmp(g_syl[i].py, py, pyl) != 0) {
      continue;
    }
    {
      const unsigned char *p = (const unsigned char *)g_syl[i].zh;
      int L;
      char first[8];

      if (*p == '\0') {
        continue;
      }
      L = utf8_len(p);
      memcpy(first, p, (size_t)L);
      first[L] = '\0';
      if (seen++ < skip) {
        continue;
      }
      n = add_one(out, cons, n, max, first, (unsigned)pyl);
    }
  }

  return n;
}
