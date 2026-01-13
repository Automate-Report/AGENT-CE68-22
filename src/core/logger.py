#จัดการ log
import logging
import sys

def setup_logger(name):
    # 1. สร้าง Formatter ที่เราอยากได้ (เลียนแบบอันที่คุณชอบใน log)
    # รูปแบบ: เวลา [LEVEL] ข้อความ
    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )

    # 2. สร้าง Handler (ตัวจัดการว่าจะพ่น log ออกทางไหน)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # 3. สร้าง Logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # 4. Clear handler เก่าทิ้งก่อน เพื่อกันซ้ำ (สำคัญมาก!)
    if logger.hasHandlers():
        logger.handlers.clear()
        
    # 5. ใส่ Handler ใหม่เข้าไป
    logger.addHandler(handler)
    
    # 6. ปิด Propagation เพื่อไม่ให้มันส่งไปหา Root Logger (กันเบิ้ล)
    logger.propagate = False

    return logger