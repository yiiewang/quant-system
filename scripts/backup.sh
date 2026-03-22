#!/bin/bash
# 量化交易系统数据备份脚本
# 用法: ./scripts/backup.sh [backup_dir]

set -e

# 配置
BACKUP_DIR="${1:-/backup/quant-system}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATA_DIR="${DATA_DIR:-./data}"
LOGS_DIR="${LOGS_DIR:-./logs}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}开始备份量化交易系统数据...${NC}"
echo "备份目录: $BACKUP_DIR"
echo "时间戳: $TIMESTAMP"

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 备份数据文件
echo -e "${YELLOW}备份数据文件...${NC}"
if [ -d "$DATA_DIR" ]; then
    tar -czf "$BACKUP_DIR/data_$TIMESTAMP.tar.gz" -C "$DATA_DIR" .
    echo -e "${GREEN}数据文件备份完成${NC}"
else
    echo -e "${RED}数据目录不存在: $DATA_DIR${NC}"
fi

# 备份日志文件
echo -e "${YELLOW}备份日志文件...${NC}"
if [ -d "$LOGS_DIR" ]; then
    tar -czf "$BACKUP_DIR/logs_$TIMESTAMP.tar.gz" -C "$LOGS_DIR" .
    echo -e "${GREEN}日志文件备份完成${NC}"
else
    echo -e "${RED}日志目录不存在: $LOGS_DIR${NC}"
fi

# 备份配置文件
echo -e "${YELLOW}备份配置文件...${NC}"
if [ -d "./config" ]; then
    tar -czf "$BACKUP_DIR/config_$TIMESTAMP.tar.gz" -C "./config" .
    echo -e "${GREEN}配置文件备份完成${NC}"
else
    echo -e "${RED}配置目录不存在${NC}"
fi

# 创建备份清单
echo -e "${YELLOW}创建备份清单...${NC}"
cat > "$BACKUP_DIR/backup_$TIMESTAMP.manifest" << EOF
Backup Manifest
===============
Timestamp: $TIMESTAMP
Date: $(date)
Host: $(hostname)
User: $(whoami)

Backup Files:
- data_$TIMESTAMP.tar.gz
- logs_$TIMESTAMP.tar.gz
- config_$TIMESTAMP.tar.gz

Data Directory: $DATA_DIR
Logs Directory: $LOGS_DIR
EOF

echo -e "${GREEN}备份清单创建完成${NC}"

# 上传到远程存储（如果配置了 AWS CLI）
if command -v aws &> /dev/null && [ -n "$AWS_BUCKET" ]; then
    echo -e "${YELLOW}上传到 S3...${NC}"
    aws s3 cp "$BACKUP_DIR/data_$TIMESTAMP.tar.gz" "s3://$AWS_BUCKET/backups/"
    aws s3 cp "$BACKUP_DIR/logs_$TIMESTAMP.tar.gz" "s3://$AWS_BUCKET/backups/"
    aws s3 cp "$BACKUP_DIR/config_$TIMESTAMP.tar.gz" "s3://$AWS_BUCKET/backups/"
    echo -e "${GREEN}S3 上传完成${NC}"
fi

# 清理旧备份
echo -e "${YELLOW}清理旧备份（保留 $RETENTION_DAYS 天）...${NC}"
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.manifest" -mtime +$RETENTION_DAYS -delete
echo -e "${GREEN}旧备份清理完成${NC}"

# 输出备份摘要
echo ""
echo -e "${GREEN}备份完成！${NC}"
echo "=================="
echo "备份文件:"
ls -lh "$BACKUP_DIR"/*_$TIMESTAMP.* 2>/dev/null || echo "无备份文件"
echo ""
echo "备份位置: $BACKUP_DIR"
echo "保留策略: $RETENTION_DAYS 天"
