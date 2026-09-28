#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ============================================================
   校园灭蚊排查系统  ——  控制台基础版本
   预案2底层方案：顺序表存储 + 文件持久化
   业务逻辑全部封装，方便后续套 EasyX 图形界面
   ============================================================ */

#define MAX_SIZE 100
#define MAX_NAME 50
#define MAX_DATE 20
#define MAX_NOTE 100
#define FILE_NAME "mosquito.txt"

/* ---------- 点位结构体 ---------- */
typedef struct {
    int id;                 /* 点位编号（主键）        */
    char location[MAX_NAME];/* 地点名称                */
    int risk;               /* 风险等级：1高 2中 3低   */
    char checker[MAX_NAME]; /* 排查人                  */
    char date[MAX_DATE];    /* 排查日期                */
    int killStatus;         /* 消杀状态：0未消杀 1已消杀 */
    char note[MAX_NOTE];    /* 备注（记录详情、说明等） */
} MosquitoPoint;

/* ---------- 顺序表 ---------- */
typedef struct {
    MosquitoPoint data[MAX_SIZE];
    int length;
} SeqList;

/* ============================================================
   顺序表操作（底层封装）
   ============================================================ */

/* 初始化顺序表 */
void listInit(SeqList *list) {
    list->length = 0;
}

/* 获取长度 */
int listLength(SeqList *list) {
    return list->length;
}

/* 按 id 查找，返回下标，未找到返回 -1 */
int findById(SeqList *list, int id) {
    for (int i = 0; i < list->length; i++) {
        if (list->data[i].id == id) return i;
    }
    return -1;
}

/* 判断 id 是否已存在 */
int isIdExist(SeqList *list, int id) {
    return findById(list, id) != -1;
}

/* 追加一条记录（到尾部） */
int listAppend(SeqList *list, MosquitoPoint p) {
    if (list->length >= MAX_SIZE) {
        printf("[提示] 顺序表已满，无法继续添加。\n");
        return 0;
    }
    if (isIdExist(list, p.id)) {
        printf("[提示] 编号 %d 已存在，请勿重复添加。\n", p.id);
        return 0;
    }
    list->data[list->length++] = p;
    return 1;
}

/* 按下标删除 */
int listRemoveAt(SeqList *list, int index) {
    if (index < 0 || index >= list->length) return 0;
    for (int i = index; i < list->length - 1; i++) {
        list->data[i] = list->data[i + 1];
    }
    list->length--;
    return 1;
}

/* ============================================================
   文件读写（持久化）
   ============================================================ */

/* 从文件加载数据 */
void loadFromFile(SeqList *list) {
    FILE *fp = fopen(FILE_NAME, "r");
    if (fp == NULL) {
        printf("[提示] 未找到 %s，首次运行将创建新文件。\n", FILE_NAME);
        return;
    }
    while (list->length < MAX_SIZE &&
           fscanf(fp, "%d|%49[^|]|%d|%49[^|]|%19[^|]|%d|%99[^\n]\n",
                  &list->data[list->length].id,
                  list->data[list->length].location,
                  &list->data[list->length].risk,
                  list->data[list->length].checker,
                  list->data[list->length].date,
                  &list->data[list->length].killStatus,
                  list->data[list->length].note) == 7) {
        list->length++;
    }
    fclose(fp);
    printf("[信息] 已从 %s 读取 %d 条记录。\n", FILE_NAME, list->length);
}

/* 保存全部数据到文件 */
void saveToFile(SeqList *list) {
    FILE *fp = fopen(FILE_NAME, "w");
    if (fp == NULL) {
        printf("[错误] 无法写入 %s！\n", FILE_NAME);
        return;
    }
    for (int i = 0; i < list->length; i++) {
        fprintf(fp, "%d|%s|%d|%s|%s|%d|%s\n",
                list->data[i].id,
                list->data[i].location,
                list->data[i].risk,
                list->data[i].checker,
                list->data[i].date,
                list->data[i].killStatus,
                list->data[i].note);
    }
    fclose(fp);
    printf("[信息] 已保存 %d 条记录到 %s。\n", list->length, FILE_NAME);
}

/* ============================================================
   默认初始化数据（广东医科大学东莞校区 7 片区）
   ============================================================ */

void buildDefaultData(SeqList *list) {
    MosquitoPoint defaults[] = {
        {1, "5-10栋宿舍+留一留二宿舍", 1, "系统初始化", "2026-09-01", 0,
         "楼下垃圾桶多、绿植密集、积水死角多，蚊虫高危滋生区"},
        {2, "1-4栋、15栋宿舍片区", 2, "系统初始化", "2026-09-01", 0,
         "生活区潮湿阴暗，蚊虫密度较高，绿植密集"},
        {3, "13-16栋宿舍片区", 2, "系统初始化", "2026-09-01", 0,
         "校园生活区，绿化带密集易积水"},
        {4, "第一食堂", 1, "系统初始化", "2026-09-01", 0,
         "后厨排水、餐厨垃圾堆积、潮湿积水，核心高危区域"},
        {5, "第二食堂", 1, "系统初始化", "2026-09-01", 0,
         "后厨排水、餐厨垃圾堆积、潮湿积水，核心高危区域"},
        {6, "中心人工湖", 1, "系统初始化", "2026-09-01", 0,
         "大面积静态水域，蚊虫幼虫主要滋生地"},
        {7, "运动场", 2, "系统初始化", "2026-09-01", 0,
         "看台缝隙、排水沟、草坪低洼积水，易滋生蚊虫"}
    };
    int count = sizeof(defaults) / sizeof(defaults[0]);
    for (int i = 0; i < count; i++) {
        listAppend(list, defaults[i]);
    }
}

/* ============================================================
   辅助函数
   ============================================================ */

const char *riskText(int risk) {
    switch (risk) {
        case 1: return "高危";
        case 2: return "中危";
        case 3: return "低危";
        default: return "未知";
    }
}

const char *killText(int s) {
    return s == 1 ? "已消杀" : "未消杀";
}

/* 打印单条记录（统一格式） */
void printPoint(MosquitoPoint *p) {
    printf("+------------------------------------------------------------+\n");
    printf("| 编号: %d\n", p->id);
    printf("| 地点: %s\n", p->location);
    printf("| 风险: %s\n", riskText(p->risk));
    printf("| 排查人: %s\n", p->checker);
    printf("| 排查日期: %s\n", p->date);
    printf("| 消杀状态: %s\n", killText(p->killStatus));
    printf("| 备注: %s\n", p->note);
    printf("+------------------------------------------------------------+\n");
}

/* 清空输入缓冲区 */
void clearInput() {
    int c;
    while ((c = getchar()) != '\n' && c != EOF);
}

/* 获取字符串（安全版，带换行去除） */
void readString(char *buf, int size) {
    fgets(buf, size, stdin);
    int len = strlen(buf);
    if (len > 0 && buf[len - 1] == '\n') buf[len - 1] = '\0';
}

/* ============================================================
   业务函数实现
   ============================================================ */

/* 1. 新增点位 */
void addPoint(SeqList *list) {
    MosquitoPoint p;
    printf("\n========== 新增灭蚊点位 ==========\n");
    if (listLength(list) >= MAX_SIZE) {
        printf("[提示] 顺序表已满，无法继续添加。\n");
        return;
    }
    printf("输入编号: ");
    scanf("%d", &p.id);
    clearInput();
    if (isIdExist(list, p.id)) {
        printf("[提示] 编号已存在，添加失败。\n");
        return;
    }
    printf("输入地点名称: ");
    readString(p.location, MAX_NAME);
    printf("输入风险等级(1高/2中/3低): ");
    scanf("%d", &p.risk);
    clearInput();
    printf("输入排查人: ");
    readString(p.checker, MAX_NAME);
    printf("输入排查日期(如2026-09-12): ");
    readString(p.date, MAX_DATE);
    printf("输入消杀状态(0未消杀/1已消杀): ");
    scanf("%d", &p.killStatus);
    clearInput();
    printf("输入备注: ");
    readString(p.note, MAX_NOTE);

    if (listAppend(list, p)) {
        printf("\n[成功] 编号 %d 的点位添加成功！\n", p.id);
    }
}

/* 2. 查看全部记录 */
void showAll(SeqList *list) {
    printf("\n========== 全部灭蚊点位记录 ==========\n");
    if (listLength(list) == 0) {
        printf("[提示] 当前没有任何记录。\n");
        return;
    }
    printf("共 %d 条记录：\n", listLength(list));
    for (int i = 0; i < listLength(list); i++) {
        printPoint(&list->data[i]);
    }
}

/* 3. 编号查询 */
void queryById(SeqList *list) {
    int id;
    printf("\n========== 编号查询 ==========\n");
    printf("输入要查询的编号: ");
    scanf("%d", &id);
    int idx = findById(list, id);
    if (idx == -1) {
        printf("[提示] 未找到编号为 %d 的点位。\n", id);
    } else {
        printPoint(&list->data[idx]);
    }
}

/* 4. 修改点位（带二级菜单） */
void modifyPoint(SeqList *list) {
    int id;
    printf("\n========== 修改灭蚊点位 ==========\n");
    printf("输入要修改的编号: ");
    scanf("%d", &id);
    int idx = findById(list, id);
    if (idx == -1) {
        printf("[提示] 未找到编号为 %d 的点位。\n", id);
        return;
    }

    int choice;
    do {
        printf("\n----- 修改二级菜单（编号 %d）-----\n", id);
        printf("  1. 修改地点\n");
        printf("  2. 修改风险等级\n");
        printf("  3. 修改排查人\n");
        printf("  4. 修改排查日期\n");
        printf("  5. 修改备注\n");
        printf("  6. 一次性全部修改\n");
        printf("  7. 完成修改\n");
        printf("请选择: ");
        scanf("%d", &choice);
        clearInput();

        switch (choice) {
            case 1:
                printf("新地点: ");
                readString(list->data[idx].location, MAX_NAME);
                printf("[成功] 地点已更新！\n");
                break;
            case 2:
                printf("新风险等级(1高/2中/3低): ");
                scanf("%d", &list->data[idx].risk);
                clearInput();
                printf("[成功] 风险等级已更新！\n");
                break;
            case 3:
                printf("新排查人: ");
                readString(list->data[idx].checker, MAX_NAME);
                printf("[成功] 排查人已更新！\n");
                break;
            case 4:
                printf("新排查日期: ");
                readString(list->data[idx].date, MAX_DATE);
                printf("[成功] 排查日期已更新！\n");
                break;
            case 5:
                printf("新备注: ");
                readString(list->data[idx].note, MAX_NOTE);
                printf("[成功] 备注已更新！\n");
                break;
            case 6:
                printf("新地点: ");
                readString(list->data[idx].location, MAX_NAME);
                printf("新风险等级(1高/2中/3低): ");
                scanf("%d", &list->data[idx].risk);
                clearInput();
                printf("新排查人: ");
                readString(list->data[idx].checker, MAX_NAME);
                printf("新排查日期: ");
                readString(list->data[idx].date, MAX_DATE);
                printf("新消杀状态(0未/1已): ");
                scanf("%d", &list->data[idx].killStatus);
                clearInput();
                printf("新备注: ");
                readString(list->data[idx].note, MAX_NOTE);
                printf("[成功] 全部字段已更新！\n");
                break;
            case 7:
                printf("[信息] 已完成修改。\n");
                break;
            default:
                printf("[提示] 无效选项，请重新选择。\n");
        }
    } while (choice != 7);
}

/* 5. 删除点位 */
void deletePoint(SeqList *list) {
    int id, confirm;
    printf("\n========== 删除灭蚊点位 ==========\n");
    printf("输入要删除的编号: ");
    scanf("%d", &id);
    int idx = findById(list, id);
    if (idx == -1) {
        printf("[提示] 未找到编号为 %d 的点位。\n", id);
        return;
    }
    printf("即将删除：\n");
    printPoint(&list->data[idx]);
    printf("确认删除？(1确认 / 其他取消): ");
    scanf("%d", &confirm);
    if (confirm == 1) {
        listRemoveAt(list, idx);
        printf("[成功] 编号 %d 已删除。\n", id);
    } else {
        printf("[取消] 已放弃删除操作。\n");
    }
}

/* 6. 数据统计 */
void statistics(SeqList *list) {
    printf("\n========== 数据统计 ==========\n");
    int total = listLength(list);
    int high = 0, mid = 0, low = 0;
    int killed = 0, notKilled = 0;
    for (int i = 0; i < total; i++) {
        if (list->data[i].risk == 1) high++;
        else if (list->data[i].risk == 2) mid++;
        else if (list->data[i].risk == 3) low++;

        if (list->data[i].killStatus == 1) killed++;
        else notKilled++;
    }
    printf("===========================================\n");
    printf("  总地点数：%d\n", total);
    printf("    高危：%d 个\n", high);
    printf("    中危：%d 个\n", mid);
    printf("    低危：%d 个\n", low);
    printf("  已消杀：%d 个\n", killed);
    printf("  未消杀：%d 个\n", notKilled);
    printf("===========================================\n");
}

/* 7. 筛选点位 —— 支持按风险等级筛选（1高 / 2中 / 3低） */
void filterByRisk(SeqList *list) {
    int risk, found = 0;
    printf("\n========== 筛选点位 ==========\n");
    printf("请选择风险等级（1高/2中/3低）：");
    scanf("%d", &risk);
    clearInput();

    if (risk != 1 && risk != 2 && risk != 3) {
        printf("[提示] 无效的风险等级输入，已取消筛选。\n");
        printf("按回车键返回主菜单...");
        clearInput();
        return;
    }

    printf("\n——— %s 风险点位筛选结果 ———\n", riskText(risk));
    for (int i = 0; i < listLength(list); i++) {
        if (list->data[i].risk == risk) {
            printPoint(&list->data[i]);
            found++;
        }
    }

    if (found == 0) {
        printf("未找到对应风险等级的点位\n");
    } else {
        printf("共找到 %d 条匹配记录\n", found);
    }

    printf("\n按回车键返回主菜单...");
    clearInput();
}

/* ============================================================
   菜单
   ============================================================ */

void showMenu() {
    printf("\n################################################\n");
    printf("#      广东医科大学东莞校区  灭蚊排查系统       #\n");
    printf("################################################\n");
    printf("  1. 新增点位\n");
    printf("  2. 查看全部记录\n");
    printf("  3. 编号查询\n");
    printf("  4. 修改点位\n");
    printf("  5. 删除点位\n");
    printf("  6. 数据统计\n");
    printf("  7. 筛选点位\n");
    printf("  0. 退出系统（自动保存）\n");
    printf("################################################\n");
    printf("请选择选项: ");
}

/* ============================================================
   main 函数
   ============================================================ */
int main() {
    SeqList list;
    listInit(&list);

    /* 启动时加载文件 */
    loadFromFile(&list);

    /* 若文件为空则载入默认初始化数据（第一次使用） */
    if (listLength(&list) == 0) {
        printf("\n[信息] 检测到空数据，正在载入广东医科大学东莞校区 7 个片区...\n");
        buildDefaultData(&list);
        printf("[信息] 初始化完成。\n");
    }

    int choice;
    do {
        showMenu();
        scanf("%d", &choice);
        clearInput();

        switch (choice) {
            case 1: addPoint(&list);        break;
            case 2: showAll(&list);         break;
            case 3: queryById(&list);       break;
            case 4: modifyPoint(&list);     break;
            case 5: deletePoint(&list);     break;
            case 6: statistics(&list);      break;
            case 7: filterByRisk(&list);    break;
            case 0: break;
            default:
                printf("[提示] 无效选项，请重新输入。\n");
        }
    } while (choice != 0);

    /* 退出时保存 */
    printf("\n[信息] 正在保存数据...\n");
    saveToFile(&list);
    printf("[信息] 再见！\n");

    return 0;
}