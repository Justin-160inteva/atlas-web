'use strict';

(() => {
  const CHAPTER6 = [
    {
      "chapter": "第6关",
      "scene": "开篇前置审讯过场",
      "order": 1,
      "speaker": "Mitchell (Narrator)",
      "en": "It was as close as we'd ever been... Four years on Hades' trail, and now we had his number two. The Doctor was the key to everything.",
      "zh": "这是我们离目标最近的一次……四年追踪冥王，如今我们抓住了他的二号人物。博士就是解开一切的钥匙。",
      "aliases": ["close we'd ever Four years"]
    },
    {
      "chapter": "第6关",
      "scene": "开篇前置审讯过场",
      "order": 2,
      "speaker": "Ilona",
      "en": "Let’s start over. Who is Hades? What’s his plan?",
      "zh": "我们重新谈一次。冥王是谁？他的全盘计划是什么？",
      "aliases": ["Let start Hades plan"]
    },
    {
      "chapter": "第6关",
      "scene": "开篇前置审讯过场",
      "order": 3,
      "speaker": "Doctor",
      "en": "You will never stop him. The Menticore program will reshape this world.",
      "zh": "你们永远阻止不了他，心智核心计划将重塑整个世界。",
      "aliases": ["never stop Menticore program reshape", "You will never stop him. The Manticore program will reshape this world."]
    },
    {
      "chapter": "第6关",
      "scene": "开篇前置审讯过场",
      "order": 4,
      "speaker": "Ilona",
      "en": "Menticore? What is it exactly?",
      "zh": "心智核心？那到底是什么？",
      "aliases": ["Menticore exactly", "Manticore? What is it exactly?"]
    },
    {
      "chapter": "第6关",
      "scene": "开篇前置审讯过场",
      "order": 5,
      "speaker": "Doctor",
      "en": "Ask your boss Irons. He already knows all about it.",
      "zh": "去问你们的老板艾恩斯，他早就清楚全部内情。",
      "aliases": ["Ask boss Irons already knows"]
    },
    {
      "chapter": "第6关",
      "scene": "五角大楼会议室",
      "order": 6,
      "speaker": "General Winston",
      "en": "Jonathan, you do not have authorization to launch a cross-border operation into Greece. The UN hasn’t signed off on this strike.",
      "zh": "乔纳森，你没有授权在希腊发起跨境行动，联合国尚未批准本次突袭。",
      "aliases": ["Jonathan authorization launch cross border"]
    },
    {
      "chapter": "第6关",
      "scene": "五角大楼会议室",
      "order": 7,
      "speaker": "Irons",
      "en": "This man is responsible for fifty thousand deaths, General. We are going in.",
      "zh": "将军，此人手上沾着五万人的鲜血，我们必须出击。",
      "aliases": ["responsible fifty thousand deaths General"]
    },
    {
      "chapter": "第6关",
      "scene": "五角大楼会议室",
      "order": 8,
      "speaker": "General Winston",
      "en": "That is not your call to make. If you deploy Atlas troops without official military clearance, you risk triggering an international diplomatic crisis.",
      "zh": "这件事轮不到你来决断。未经军方正式许可擅自调动巨神武装，会引发严重国际外交危机。",
      "aliases": ["call make deploy Atlas troops"]
    },
    {
      "chapter": "第6关",
      "scene": "五角大楼会议室",
      "order": 9,
      "speaker": "Irons",
      "en": "Four nuclear meltdowns across North America, Europe, Asia. Tens of thousands dead, millions displaced. Your governments sat back and watched while KVA burned cities to the ground. Atlas does not wait for red tape.",
      "zh": "北美、欧洲、亚洲四起核堆熔毁灾难，数万民众遇难，数百万人流离失所。你们各国政府坐视KVA将一座座城市化为焦土，而巨神不会坐等官僚流程。",
      "aliases": ["Four nuclear meltdowns across North"]
    },
    {
      "chapter": "第6关",
      "scene": "五角大楼会议室",
      "order": 10,
      "speaker": "General Winston",
      "en": "I order you to stand your men down. Hold position until we negotiate a formal joint task force.",
      "zh": "我命令你召回你的部队，原地待命，等待我们协商组建官方联合特遣队。",
      "aliases": ["order stand men Hold position"]
    },
    {
      "chapter": "第6关",
      "scene": "五角大楼会议室",
      "order": 11,
      "speaker": "Irons",
      "en": "My team leaves at dawn. With or without your approval.",
      "zh": "我的小队黎明出发，无论你是否批准。",
      "aliases": ["team leaves dawn approval"]
    },
    {
      "chapter": "第6关",
      "scene": "五角大楼会议室",
      "order": 12,
      "speaker": "General Winston",
      "en": "You will regret this, Irons. This reckless disregard for global military protocol will come back to haunt you.",
      "zh": "你会为今天的决定后悔，艾恩斯。这种无视全球军事准则的鲁莽行径终将反噬你自己。",
      "aliases": ["regret Irons reckless disregard global"]
    },
    {
      "chapter": "第6关",
      "scene": "五角大楼会议室",
      "order": 13,
      "speaker": "Irons",
      "en": "Let history judge who acted responsibly.",
      "zh": "是非功过，自有历史评判。",
      "aliases": ["Let history judge acted responsibly"]
    },
    {
      "chapter": "第6关",
      "scene": "Atlas运输机行动简报",
      "order": 14,
      "speaker": "Irons (Hologram)",
      "en": "Team, I don't need to remind you how important this mission is. Hades is responsible for the nuclear attacks four years ago. We bring him down, we bring down the whole KVA network. There's no room for error. Get it done.",
      "zh": "各位队员，无需我重申本次任务的重要性。四年前多起核袭击的元凶就是冥王。拿下他，就能彻底摧毁KVA整个恐怖网络，本次行动不容许任何失误，务必完成任务。",
      "aliases": ["Team don't need remind important"]
    },
    {
      "chapter": "第6关",
      "scene": "Atlas运输机行动简报",
      "order": 15,
      "speaker": "Gideon",
      "en": "Santorini civilian market, broad daylight. Hades will have heavy security everywhere.",
      "zh": "目标地点圣托里尼露天集市，行动在白天进行，冥王必定布下重重守卫。",
      "aliases": ["Santorini civilian market broad daylight"]
    },
    {
      "chapter": "第6关",
      "scene": "Atlas运输机行动简报",
      "order": 16,
      "speaker": "Ilona",
      "en": "Our only window is during his private summit with regional KVA cell leaders. We track their middleman \"Key-Man\" first, follow him straight to Hades.",
      "zh": "唯一机会是他与各地KVA分部头目密会期间。我们先找到中间人“关键人”，尾随他直达冥王藏身点。",
      "aliases": ["only window during private summit"]
    },
    {
      "chapter": "第6关",
      "scene": "Atlas运输机行动简报",
      "order": 17,
      "speaker": "Mitchell",
      "en": "If we blow the Key-Man’s cover, Hades slips away before we get close.",
      "zh": "一旦暴露关键人，冥王会在我们靠近前脱身。",
      "aliases": ["blow Key Man cover Hades"]
    },
    {
      "chapter": "第6关",
      "scene": "Atlas运输机行动简报",
      "order": 18,
      "speaker": "Ilona",
      "en": "Exo cloaks and suppressed weapons only. Non-lethal takedowns first, we cannot raise a city-wide alert.",
      "zh": "外骨骼隐身与消音武器全程开启，优先使用非致命制伏，不能触发全城警戒。",
      "aliases": ["Exo cloaks suppressed weapons Non"]
    },
    {
      "chapter": "第6关",
      "scene": "圣托里尼集市潜行",
      "order": 19,
      "speaker": "Ilona",
      "en": "Split into pairs. Mitchell, stick with me. Gideon, cover the west market stalls.",
      "zh": "两人一组分散行动。米切尔跟我一组，吉迪恩去西侧摊位警戒。",
      "aliases": ["Split pairs Mitchell stick Gideon"]
    },
    {
      "chapter": "第6关",
      "scene": "圣托里尼集市潜行",
      "order": 20,
      "speaker": "Gideon",
      "en": "Copy. I’ve got thermal scopes on my visor, scanning for armed hostiles.",
      "zh": "收到，头盔热成像正在扫描武装人员。",
      "aliases": ["Copy got thermal scopes visor"]
    },
    {
      "chapter": "第6关",
      "scene": "圣托里尼集市潜行",
      "order": 21,
      "speaker": "Ilona",
      "en": "Target Key-Man is wearing a dark hooded jacket, loitering by the wine vendor. Don’t approach head-on, loop around the back alley.",
      "zh": "目标关键人身穿深色连帽外套，在葡萄酒摊贩旁逗留，不要正面接近，从后方小巷迂回。",
      "aliases": ["Target Key Man wearing dark"]
    },
    {
      "chapter": "第6关",
      "scene": "圣托里尼集市潜行",
      "order": 22,
      "speaker": "Mitchell",
      "en": "Civilians everywhere, can’t risk firefight here.",
      "zh": "集市遍布平民，不能在此交火。",
      "aliases": ["Civilians everywhere risk firefight"]
    },
    {
      "chapter": "第6关",
      "scene": "圣托里尼集市潜行",
      "order": 23,
      "speaker": "Ilona",
      "en": "Use exo taser punches if guards spot us, no live rounds unless our lives are threatened.",
      "zh": "守卫发现我们就用外骨骼电击拳，除非生命受威胁，禁止实弹射击。",
      "aliases": ["Use exo taser punches guards"]
    },
    {
      "chapter": "第6关",
      "scene": "圣托里尼集市潜行",
      "order": 24,
      "speaker": "Gideon",
      "en": "Multiple patrols circling the central fountain, their radio comms are active.",
      "zh": "中央喷泉周边多支巡逻队来回巡逻，无线电全程保持通讯。",
      "aliases": ["Multiple patrols circling central fountain"]
    },
    {
      "chapter": "第6关",
      "scene": "圣托里尼集市潜行",
      "order": 25,
      "speaker": "Ilona",
      "en": "The Key-Man’s moving toward the cliffside villa. Follow his trail, stay out of sight.",
      "zh": "关键人往悬崖别墅方向移动，跟上他，全程隐蔽。",
      "aliases": ["Key Man moving toward cliffside"]
    },
    {
      "chapter": "第6关",
      "scene": "别墅外围交火与抓捕",
      "order": 26,
      "speaker": "Gideon",
      "en": "Heavy machine gun emplacements at every gate, rooftop snipers.",
      "zh": "所有大门都架设重机枪，楼顶还有狙击手。",
      "aliases": ["Heavy machine gun emplacements every"]
    },
    {
      "chapter": "第6关",
      "scene": "别墅外围交火与抓捕",
      "order": 27,
      "speaker": "Ilona",
      "en": "Mitchell, breach the coastal drainage tunnel—we’ll sneak in underground.",
      "zh": "米切尔，从海边排水管道突入，我们走地下迂回潜入。",
      "aliases": ["Mitchell breach coastal drainage tunnel"]
    },
    {
      "chapter": "第6关",
      "scene": "别墅外围交火与抓捕",
      "order": 28,
      "speaker": "Gideon",
      "en": "They’ve got drone sentries patrolling the gardens!",
      "zh": "花园里还有巡逻无人机！",
      "aliases": ["They got drone sentries patrolling"]
    },
    {
      "chapter": "第6关",
      "scene": "别墅外围交火与抓捕",
      "order": 29,
      "speaker": "Mitchell",
      "en": "I’ll hack the drone control panel, disable their surveillance feed.",
      "zh": "我去黑入无人机控制台，切断监控信号。",
      "aliases": ["hack drone control panel disable"]
    },
    {
      "chapter": "第6关",
      "scene": "别墅外围交火与抓捕",
      "order": 30,
      "speaker": "Chkheidze (Key-Man)",
      "en": "Don’t kill me! I’ll tell you everything about Hades!",
      "zh": "别杀我！我把冥王的全部情报都交代出来！",
      "aliases": ["Don kill tell everything Hades"]
    },
    {
      "chapter": "第6关",
      "scene": "别墅外围交火与抓捕",
      "order": 31,
      "speaker": "Ilona",
      "en": "Where is Hades holding the summit? Give us the exact villa coordinates.",
      "zh": "冥王在哪开密会？交出别墅精确坐标。",
      "aliases": ["Hades holding summit Give exact"]
    },
    {
      "chapter": "第6关",
      "scene": "别墅外围交火与抓捕",
      "order": 32,
      "speaker": "Chkheidze (Key-Man)",
      "en": "The private cliff mansion north of the village. But you need to know—",
      "zh": "村庄北侧悬崖私人庄园，但你们必须清楚——",
      "aliases": ["private cliff mansion north village"]
    },
    {
      "chapter": "第6关",
      "scene": "别墅外围交火与抓捕",
      "order": 33,
      "speaker": "Chkheidze (Dying)",
      "en": "Irons knows…",
      "zh": "艾恩斯……他全都知道……",
      "aliases": ["Irons knows"]
    },
    {
      "chapter": "第6关",
      "scene": "别墅外围交火与抓捕",
      "order": 34,
      "speaker": "Ilona",
      "en": "Sniper on the far ridge! He was sent to silence the witness!",
      "zh": "远处山脊有狙击手，对方专门来灭口！",
      "aliases": ["Sniper far ridge sent silence"]
    },
    {
      "chapter": "第6关",
      "scene": "别墅外围交火与抓捕",
      "order": 35,
      "speaker": "Gideon",
      "en": "Hades knew we’d track the Key-Man, this was a trap.",
      "zh": "冥王早料到我们会追踪关键人，这从头到尾都是陷阱。",
      "aliases": ["Hades knew track Key Man"]
    },
    {
      "chapter": "第6关",
      "scene": "撤离突围与关卡结尾",
      "order": 36,
      "speaker": "Ilona",
      "en": "Extraction boat’s waiting on the south shore, we need to break through the villa front gate!",
      "zh": "撤离船停靠南岸海滩，我们必须冲开别墅正门突围！",
      "aliases": ["Extraction boat waiting south shore"]
    },
    {
      "chapter": "第6关",
      "scene": "撤离突围与关卡结尾",
      "order": 37,
      "speaker": "Mitchell",
      "en": "Their reinforcements keep pouring in, the villa is surrounded.",
      "zh": "敌军增援源源不断，整栋别墅已经被彻底包围。",
      "aliases": ["reinforcements keep pouring villa surrounded"]
    },
    {
      "chapter": "第6关",
      "scene": "撤离突围与关卡结尾",
      "order": 38,
      "speaker": "Gideon",
      "en": "Grab the exo rocket launchers by the patio, clear a path to the gate!",
      "zh": "拿露台的外骨骼火箭筒，轰开一条通往大门的通路！",
      "aliases": ["Grab exo rocket launchers patio"]
    },
    {
      "chapter": "第6关",
      "scene": "撤离突围与关卡结尾",
      "order": 39,
      "speaker": "Mitchell (Narrator)",
      "en": "The Key-Man’s final words haunted me. Irons knows. What exactly did the Doctor and this middleman mean? The line between our employer and our enemy was starting to blur.",
      "zh": "关键人临终那句话始终萦绕在我脑海——艾恩斯全都知道。博士和这名中间人到底想暗示什么？雇主与敌人之间的界限，开始变得模糊不清。",
      "aliases": ["Key Man final words haunted"]
    }
  ];

  const chapterName = '第6关';
  const existing = Array.isArray(state.library) ? state.library : [];
  const retained = existing.filter(item => item?.chapter !== chapterName && item?.chapter !== '演示');
  state.library = [...retained, ...CHAPTER6];
  saveLibrary();
  if (typeof refreshLibraryUI === 'function') refreshLibraryUI();
  window.COD11_CHAPTER6_LIBRARY = CHAPTER6;
})();
