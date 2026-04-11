"""
Seed data for Sawasdee — generates demo users with random avatars.
Uses pravatar.cc and randomuser.me for realistic profile photos.
"""
import uuid
import random
from datetime import datetime, timedelta
from app.models.user import User, Gender, Nationality
from app.models.post import Post, Story
from app.models.album import Album, Photo, AlbumType
from app.services.auth import get_password_hash

# ============================================================
# Thai female names & profiles
# ============================================================
THAI_FEMALES = [
    {
        "display_name": "Ploy",
        "username": "ploy_bkk",
        "age": 24,
        "height": 162,
        "weight": 48,
        "cup_size": "C",
        "location": "Bangkok",
        "interests": "旅遊, 美食, 瑜伽, 攝影",
        "bio": "สวัสดีค่ะ 🌸 ชอบเที่ยวและถ่ายรูป อยากรู้จักคนไต้หวัน / 喜歡旅行和拍照，想認識台灣朋友 ❤️",
        "avatar_url": "https://randomuser.me/api/portraits/women/1.jpg",
    },
    {
        "display_name": "Mintra",
        "username": "mintra_cm",
        "age": 22,
        "height": 158,
        "weight": 45,
        "cup_size": "B",
        "location": "Chiang Mai",
        "interests": "咖啡, 音樂, 畫畫, 寵物",
        "bio": "เด็กเชียงใหม่ค่ะ ชอบกาแฟและดนตรี ☕🎵 / 清邁女孩，喜歡咖啡和音樂",
        "avatar_url": "https://randomuser.me/api/portraits/women/2.jpg",
    },
    {
        "display_name": "Fern",
        "username": "fern_sweet",
        "age": 26,
        "height": 165,
        "weight": 50,
        "cup_size": "D",
        "location": "Phuket",
        "interests": "潛水, 海灘, 健身, 料理",
        "bio": "ชอบทะเลและดำน้ำ 🌊 ทำอาหารไทยเก่ง / 愛海愛潛水，擅長泰國料理 🍜",
        "avatar_url": "https://randomuser.me/api/portraits/women/3.jpg",
    },
    {
        "display_name": "Namwan",
        "username": "namwan_22",
        "age": 23,
        "height": 160,
        "weight": 46,
        "cup_size": "B",
        "location": "Bangkok",
        "interests": "K-pop, 購物, 甜點, 追劇",
        "bio": "ชอบ K-pop และช้อปปิ้ง 💕 อยากไปไต้หวัน / K-pop 迷，想去台灣玩！",
        "avatar_url": "https://randomuser.me/api/portraits/women/4.jpg",
    },
    {
        "display_name": "Pim",
        "username": "pim_pattaya",
        "age": 25,
        "height": 168,
        "weight": 52,
        "cup_size": "C",
        "location": "Pattaya",
        "interests": "夜生活, DJ, 時尚, 旅遊",
        "bio": "DJ สาวพัทยา 🎧 ชอบเที่ยวกลางคืนและแฟชั่น / 芭達雅 DJ 女孩，熱愛時尚 ✨",
        "avatar_url": "https://randomuser.me/api/portraits/women/5.jpg",
    },
    {
        "display_name": "Opal",
        "username": "opal_nurse",
        "age": 27,
        "height": 157,
        "weight": 47,
        "cup_size": "B",
        "location": "Bangkok",
        "interests": "醫療, 閱讀, 烹飪, 園藝",
        "bio": "พยาบาลค่ะ 👩‍⚕️ ชอบอ่านหนังสือและทำอาหาร / 護理師，喜歡閱讀和做菜 📚",
        "avatar_url": "https://randomuser.me/api/portraits/women/6.jpg",
    },
    {
        "display_name": "Praew",
        "username": "praew_model",
        "age": 24,
        "height": 172,
        "weight": 53,
        "cup_size": "D",
        "location": "Bangkok",
        "interests": "模特, 健身, 瑜伽, 旅遊",
        "bio": "นางแบบค่ะ ชอบออกกำลังกายและโยคะ 💪 / 模特兒，熱愛健身和瑜伽",
        "avatar_url": "https://randomuser.me/api/portraits/women/7.jpg",
    },
    {
        "display_name": "Nuch",
        "username": "nuch_art",
        "age": 23,
        "height": 155,
        "weight": 44,
        "cup_size": "A",
        "location": "Chiang Rai",
        "interests": "藝術, 手作, 咖啡, 自然",
        "bio": "ศิลปินค่ะ 🎨 ชอบธรรมชาติและงานฝีมือ / 藝術家，喜歡大自然和手工藝",
        "avatar_url": "https://randomuser.me/api/portraits/women/8.jpg",
    },
    {
        "display_name": "Bow",
        "username": "bow_bkk",
        "age": 28,
        "height": 163,
        "weight": 49,
        "cup_size": "C",
        "location": "Bangkok",
        "interests": "金融, 投資, 旅遊, 美食",
        "bio": "ทำงานด้านการเงิน 💼 ชอบเที่ยวและกินอาหารอร่อย / 金融業，愛吃愛旅遊",
        "avatar_url": "https://randomuser.me/api/portraits/women/9.jpg",
    },
    {
        "display_name": "Bam",
        "username": "bam_fitness",
        "age": 25,
        "height": 166,
        "weight": 51,
        "cup_size": "E",
        "location": "Bangkok",
        "interests": "健身, 營養, 跳舞, 攝影",
        "bio": "เทรนเนอร์ค่ะ 💪 ชอบออกกำลังกายและเต้น / 健身教練，熱愛運動和舞蹈 💃",
        "avatar_url": "https://randomuser.me/api/portraits/women/10.jpg",
    },
    {
        "display_name": "Ice",
        "username": "ice_sweet23",
        "age": 21,
        "height": 159,
        "weight": 45,
        "cup_size": "B",
        "location": "Khon Kaen",
        "interests": "大學生, 音樂, 電影, 旅遊",
        "bio": "นักศึกษาค่ะ 📖 ชอบดูหนังและฟังเพลง / 大學生，愛看電影聽音樂 🎬",
        "avatar_url": "https://randomuser.me/api/portraits/women/11.jpg",
    },
    {
        "display_name": "Kratae",
        "username": "kratae_thai",
        "age": 26,
        "height": 161,
        "weight": 48,
        "cup_size": "C",
        "location": "Bangkok",
        "interests": "泰拳, 健身, 美食, 夜市",
        "bio": "ชอบมวยไทยและกินของอร่อย 🥊🍜 / 泰拳愛好者，夜市控",
        "avatar_url": "https://randomuser.me/api/portraits/women/12.jpg",
    },
]

# ============================================================
# Taiwanese male names & profiles
# ============================================================
TAIWANESE_MALES = [
    {
        "display_name": "Kevin",
        "username": "kevin_tw",
        "age": 28,
        "height": 178,
        "weight": 75,
        "location": "台北",
        "interests": "科技, 健身, 旅遊, 攝影",
        "bio": "軟體工程師 💻 喜歡旅遊和攝影，去過泰國三次了！想認識泰國朋友 🇹🇭",
        "avatar_url": "https://randomuser.me/api/portraits/men/1.jpg",
    },
    {
        "display_name": "Jason",
        "username": "jason_taipei",
        "age": 30,
        "height": 175,
        "weight": 72,
        "location": "台北",
        "interests": "美食, 咖啡, 電影, 健身",
        "bio": "在台北開咖啡店 ☕ 很喜歡泰國文化，希望找到真愛 ❤️",
        "avatar_url": "https://randomuser.me/api/portraits/men/2.jpg",
    },
    {
        "display_name": "William",
        "username": "will_hsinchu",
        "age": 27,
        "height": 180,
        "weight": 78,
        "location": "新竹",
        "interests": "工程, 登山, 單車, 音樂",
        "bio": "竹科工程師 🔧 假日喜歡登山騎車，想找一個溫柔的女孩一起探險",
        "avatar_url": "https://randomuser.me/api/portraits/men/3.jpg",
    },
    {
        "display_name": "Eric",
        "username": "eric_foodie",
        "age": 26,
        "height": 173,
        "weight": 68,
        "location": "台中",
        "interests": "料理, 美食, 旅遊, 潛水",
        "bio": "廚師 👨‍🍳 專精泰式料理，想找泰國女孩教我道地泰菜 🍜",
        "avatar_url": "https://randomuser.me/api/portraits/men/4.jpg",
    },
    {
        "display_name": "David",
        "username": "david_travel",
        "age": 32,
        "height": 176,
        "weight": 74,
        "location": "高雄",
        "interests": "旅遊, 潛水, 攝影, 衝浪",
        "bio": "旅遊部落客 ✈️ 每年都去泰國，會說一點泰語 สวัสดีครับ",
        "avatar_url": "https://randomuser.me/api/portraits/men/5.jpg",
    },
    {
        "display_name": "Mark",
        "username": "mark_gym",
        "age": 29,
        "height": 182,
        "weight": 82,
        "location": "台北",
        "interests": "健身, 籃球, 音樂, 夜生活",
        "bio": "健身教練 💪 喜歡夜生活和音樂，個性開朗外向",
        "avatar_url": "https://randomuser.me/api/portraits/men/6.jpg",
    },
    {
        "display_name": "Andy",
        "username": "andy_design",
        "age": 25,
        "height": 174,
        "weight": 65,
        "location": "台北",
        "interests": "設計, 藝術, 咖啡, 音樂",
        "bio": "UI 設計師 🎨 喜歡藝術和咖啡，想找有共同興趣的女孩",
        "avatar_url": "https://randomuser.me/api/portraits/men/7.jpg",
    },
    {
        "display_name": "Chris",
        "username": "chris_biz",
        "age": 33,
        "height": 177,
        "weight": 76,
        "location": "台北",
        "interests": "創業, 投資, 高爾夫, 紅酒",
        "bio": "經營電商公司 📊 常去曼谷出差，想認識在地泰國朋友",
        "avatar_url": "https://randomuser.me/api/portraits/men/8.jpg",
    },
    {
        "display_name": "Leo",
        "username": "leo_music",
        "age": 24,
        "height": 170,
        "weight": 63,
        "location": "台南",
        "interests": "音樂, 吉他, 唱歌, 夜市",
        "bio": "音樂人 🎸 在台南玩樂團，喜歡泰國音樂文化",
        "avatar_url": "https://randomuser.me/api/portraits/men/9.jpg",
    },
    {
        "display_name": "Ryan",
        "username": "ryan_photo",
        "age": 27,
        "height": 179,
        "weight": 73,
        "location": "桃園",
        "interests": "攝影, 旅遊, 登山, 露營",
        "bio": "攝影師 📸 專門拍風景和人像，想幫泰國女孩拍美照",
        "avatar_url": "https://randomuser.me/api/portraits/men/10.jpg",
    },
    {
        "display_name": "Tom",
        "username": "tom_doctor",
        "age": 31,
        "height": 175,
        "weight": 70,
        "location": "台北",
        "interests": "醫療, 閱讀, 瑜伽, 旅遊",
        "bio": "醫生 👨‍⚕️ 工作忙碌但很重感情，想找一個溫暖的伴侶",
        "avatar_url": "https://randomuser.me/api/portraits/men/11.jpg",
    },
    {
        "display_name": "Howard",
        "username": "howard_fin",
        "age": 29,
        "height": 181,
        "weight": 77,
        "location": "台北",
        "interests": "金融, 股票, 健身, 威士忌",
        "bio": "投資銀行工作 📈 喜歡健身和品酒，尋找人生伴侶",
        "avatar_url": "https://randomuser.me/api/portraits/men/12.jpg",
    },
]

# ============================================================
# Sample posts content
# ============================================================
FEMALE_POSTS = [
    "วันนี้อากาศดีจัง ☀️ ไปเที่ยวกัน / 今天天氣真好，一起出去玩吧！",
    "ทำต้มยำกุ้งเองค่ะ 🍜 อร่อยมาก / 自己做的酸辣蝦湯，超好吃！",
    "ชอบไต้หวันมากค่ะ อยากไปอีก 🇹🇼 / 超喜歡台灣，想再去一次",
    "โยคะเช้านี้ 🧘‍♀️ สดชื่นมาก / 早晨瑜伽，神清氣爽",
    "คิดถึงชานมไข่มุก 🧋 / 好想念珍珠奶茶",
    "สวัสดีวันจันทร์ค่ะ 💕 ขอให้เป็นสัปดาห์ที่ดี / 星期一快樂，祝大家有美好的一週",
]

MALE_POSTS = [
    "曼谷街頭美食真的太讚了 🍜 每次來都吃不停",
    "今天在健身房練了兩小時 💪 越來越壯了",
    "泰國的寺廟真的很美，文化好豐富 🛕",
    "分享一下今天在海邊拍的照片 📸🌊",
    "學了一句新的泰語：สวัสดีครับ 哈哈還在努力學習中",
    "台北下雨了 🌧️ 好想念泰國的陽光",
]

# ============================================================
# Extra gallery photos (using picsum for variety)
# ============================================================
FEMALE_GALLERY = [
    "https://randomuser.me/api/portraits/women/{}.jpg",
]
MALE_GALLERY = [
    "https://randomuser.me/api/portraits/men/{}.jpg",
]


def generate_seed_users():
    """Generate all seed User objects."""
    users = []
    password_hash = get_password_hash("demo1234")

    for i, f in enumerate(THAI_FEMALES):
        users.append(User(
            id=uuid.uuid4(),
            email=f"{f['username']}@sawasdee.demo",
            username=f["username"],
            hashed_password=password_hash,
            display_name=f["display_name"],
            gender=Gender.female,
            nationality=Nationality.thai,
            avatar_url=f["avatar_url"],
            age=f["age"],
            height=f["height"],
            weight=f["weight"],
            cup_size=f.get("cup_size", ""),
            location=f["location"],
            interests=f["interests"],
            bio=f["bio"],
            is_subscribed=True,
            is_active=True,
            is_online=random.choice([True, True, False]),
        ))

    for i, m in enumerate(TAIWANESE_MALES):
        users.append(User(
            id=uuid.uuid4(),
            email=f"{m['username']}@sawasdee.demo",
            username=m["username"],
            hashed_password=password_hash,
            display_name=m["display_name"],
            gender=Gender.male,
            nationality=Nationality.taiwanese,
            avatar_url=m["avatar_url"],
            age=m["age"],
            height=m["height"],
            weight=m["weight"],
            cup_size="",
            location=m["location"],
            interests=m["interests"],
            bio=m["bio"],
            is_subscribed=True,
            is_active=True,
            is_online=random.choice([True, True, False]),
        ))

    return users


def generate_seed_posts(users):
    """Generate demo posts for all seed users."""
    posts = []
    now = datetime.utcnow()

    female_users = [u for u in users if u.gender == Gender.female]
    male_users = [u for u in users if u.gender == Gender.male]

    for i, u in enumerate(female_users):
        content = FEMALE_POSTS[i % len(FEMALE_POSTS)]
        posts.append(Post(
            id=uuid.uuid4(),
            author_id=u.id,
            content=content,
            image_url="",
            likes_count=random.randint(3, 25),
            comments_count=random.randint(0, 8),
            created_at=now - timedelta(hours=random.randint(1, 72)),
        ))

    for i, u in enumerate(male_users):
        content = MALE_POSTS[i % len(MALE_POSTS)]
        posts.append(Post(
            id=uuid.uuid4(),
            author_id=u.id,
            content=content,
            image_url="",
            likes_count=random.randint(2, 20),
            comments_count=random.randint(0, 5),
            created_at=now - timedelta(hours=random.randint(1, 72)),
        ))

    return posts


def generate_seed_albums(users):
    """Generate demo albums for female users."""
    albums = []
    photos = []

    female_users = [u for u in users if u.gender == Gender.female]

    for i, u in enumerate(female_users):
        # Public album
        pub_album = Album(
            id=uuid.uuid4(),
            owner_id=u.id,
            title="生活日常",
            album_type=AlbumType.public,
            cover_url=f"https://picsum.photos/seed/pub{i}/400/400",
            photo_count=3,
        )
        albums.append(pub_album)

        for j in range(3):
            photos.append(Photo(
                id=uuid.uuid4(),
                album_id=pub_album.id,
                image_url=f"https://picsum.photos/seed/photo{i}_{j}/600/600",
                caption=["日常 ☀️", "出去玩 🌊", "美食 🍜"][j],
            ))

        # Private album
        priv_album = Album(
            id=uuid.uuid4(),
            owner_id=u.id,
            title="私密相簿 🔒",
            album_type=AlbumType.private,
            cover_url="",
            photo_count=2,
        )
        albums.append(priv_album)

        for j in range(2):
            photos.append(Photo(
                id=uuid.uuid4(),
                album_id=priv_album.id,
                image_url=f"https://picsum.photos/seed/priv{i}_{j}/600/600",
                caption="",
            ))

    return albums, photos


def generate_seed_stories(users):
    """Generate active stories for some users."""
    stories = []
    now = datetime.utcnow()

    # Pick 6 random users to have active stories
    story_users = random.sample(users, min(6, len(users)))

    for i, u in enumerate(story_users):
        stories.append(Story(
            id=uuid.uuid4(),
            author_id=u.id,
            image_url=f"https://picsum.photos/seed/story{i}/400/700",
            caption=["好天氣 ☀️", "今日穿搭", "美食分享", "旅遊中", "健身打卡", "晚安 🌙"][i % 6],
            is_active=True,
            created_at=now - timedelta(hours=random.randint(1, 20)),
            expires_at=now + timedelta(hours=random.randint(2, 12)),
        ))

    return stories
