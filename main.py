class TicketLaunch(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
    
    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.success, custom_id="o_final")
    async def open(self, i, b):
        try:
            await i.response.defer(ephemeral=True)
            
            reasons = []
            admin_roles_list = []
            category_id = None
            
            # 1. جلب خيارات التذاكر وإعدادات الرتب والفئة من قاعدة البيانات
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT id, reason FROM ticket_reasons WHERE guild_id=?", (str(i.guild.id),))
                reasons = cursor.fetchall()
                
                cursor.execute("SELECT admin_roles, category_id FROM config WHERE guild_id=?", (str(i.guild.id),))
                config_row = cursor.fetchone()
                if config_row:
                    if config_row[0]:
                        admin_roles_list = config_row[0].split(",")
                    if config_row[1]:
                        category_id = config_row[1]
                conn.close()
            except Exception as db_err:
                log_error("GET_REASONS_AND_CONFIG", str(db_err))

            # 2. إعداد الصلاحيات الخاصة بالقناة لحمايتها ومنع رتبة الجميع
            overwrites = {
                # إخفاء القناة عن الجميع افتراضياً
                i.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                # السماح لصاحب التذكرة برؤية القناة والتفاعل بها
                i.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                # السماح للبوت بالتحكم الكامل
                i.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
            }

            # السماح للرتب الإدارية المحددة في لوحة التحكم برؤية القناة وإدارتها
            for role_id_str in admin_roles_list:
                try:
                    role_id = int(role_id_str)
                    role = i.guild.get_role(role_id)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
                except Exception:
                    pass

            # 3. الحصول على فئة التذاكر المحددة (إن وجدت)
            target_category = None
            if category_id:
                try:
                    target_category = i.guild.get_channel(int(category_id))
                    if not target_category:
                        target_category = await i.guild.fetch_channel(int(category_id))
                except Exception as cat_err:
                    log_error("GET_CATEGORY_ON_OPEN", str(cat_err))

            # 4. إنشاء القناة مع تطبيق الصلاحيات المخصصة والفئة
            ch = await i.guild.create_text_channel(
                name=f"ticket-{i.user.name}",
                category=target_category,
                overwrites=overwrites
            )
            await i.followup.send(f"✅ تم فتح تذكرتك: {ch.mention}", ephemeral=True)
            
            if reasons:
                await ch.send(f"أهلاً {i.user.mention}\nالرجاء تحديد سبب فتح التذكرة من القائمة أدناه للبدء:", view=TicketReasonView(reasons))
            else:
                await ch.send(f"أهلاً {i.user.mention}\nاختر الإجراء المطلوب:", view=TicketActions())
                
            log_action_db("TICKET_OPEN", str(i.user.id), f"فتح تذكرة جديدة: {ch.name}")
        except Exception as e:
            log_error("TICKET_OPEN", str(e))
            try:
                await i.followup.send("❌ حدث خطأ في فتح التذكرة!", ephemeral=True)
            except:
                pass
