api-get {{url}}/api/apps/com.vnpt.vnpttoken.vneid/reviews:
{
    "total": 3,
    "page": 1,
    "pageSize": 20,
    "reviews": [
        {
            "id": 1,
            "reviewId": null,
            "type": "review",
            "author": {
                "type": "user",
                "name": "Người dùng VNeID 1",
                "avatar": "https://ui-avatars.com/api/?name=V1"
            },
            "rating": 2,
            "content": "áp tệ + đểu . áp dùng chán . thật sự tệ . mất đt yêu cầu xác nhận khuôn mặt gửi ôtô bên vneid trả lời thành công vào kích hoat là ok mà vào thì nó cứ bắt xác nhân khuôn mặt lại từ đầu. áp nhà nước k bằng áp tư nhân. áp tệ+ đểu",
            "createdAt": "2026-06-26T10:00:00+07:00",
            "absaStatus": "labeled",
            "botReplyStatus": "pending"
        },
        {
            "id": 2,
            "reviewId": null,
            "type": "review",
            "author": {
                "type": "user",
                "name": "Người dùng VNeID 2",
                "avatar": "https://ui-avatars.com/api/?name=V2"
            },
            "rating": 1,
            "content": "app quốc gia mà cứ xài là lỗi, không gửi otp về để đăng nhập, làm không ra gì mà cứ to mồm thay đổi",
            "createdAt": "2026-06-20T09:30:00+07:00",
            "absaStatus": "labeled",
            "botReplyStatus": "pending"
        },
        {
            "id": 4,
            "reviewId": null,
            "type": "review",
            "author": {
                "type": "user",
                "name": "Người dùng VNeID 3",
                "avatar": "https://ui-avatars.com/api/?name=V3"
            },
            "rating": 2,
            "content": "app đang có 1 vài lỗi mới.",
            "createdAt": "2026-06-28T11:00:00+07:00",
            "absaStatus": "pending",
            "botReplyStatus": "replied"
        }
    ],
    "comments": [
        {
            "id": 5,
            "reviewId": 4,
            "type": "comment",
            "author": {
                "type": "bot",
                "name": "Bot Support"
            },
            "content": "bạn có thể mô tả lỗi chi tiết cho tôi được không.",
            "createdAt": "2026-06-28T11:02:00+07:00",
            "absaStatus": null,
            "botReplyStatus": null
        },
        {
            "id": 6,
            "reviewId": 4,
            "type": "comment",
            "author": {
                "type": "user",
                "name": "Người dùng VNeID 3"
            },
            "content": "lỗi đăng ký account mới không gửi mail xác nhận.",
            "createdAt": "2026-06-28T11:05:00+07:00",
            "absaStatus": "pending",
            "botReplyStatus": "pending"
        }
    ]
}