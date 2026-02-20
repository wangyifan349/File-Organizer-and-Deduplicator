import face_recognition
import numpy as np

# 封装成一个函数，直接返回相似度
def get_face_similarity(image_path1, image_path2):
    # 加载图片并获取人脸特征
    face_encoding_1 = face_recognition.face_encodings(face_recognition.load_image_file(image_path1))[0]
    face_encoding_2 = face_recognition.face_encodings(face_recognition.load_image_file(image_path2))[0]
    
    # 计算余弦相似度
    dot_product = np.dot(face_encoding_1, face_encoding_2)
    norm1 = np.linalg.norm(face_encoding_1)
    norm2 = np.linalg.norm(face_encoding_2)
    similarity = dot_product / (norm1 * norm2)
    
    return similarity

# 示例调用
similarity = get_face_similarity("person1.jpg", "person2.jpg")
print(f"余弦相似度: {similarity}")
